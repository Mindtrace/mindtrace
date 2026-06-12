"""Presigned-download round-trip test — mirrors the Chiron inference-bridge → runs path.

What this exercises (the exact calls Chiron will make):

  WRITE  (bridge today, datalake_writer._save_one_captured_image):
      asset = await vault.save("{analytic_id}/{pov}", raw_bytes, kind="image",
                               media_type="image/png")
      reference = asset.asset_id          # ← stored in Media.uri (bucket="datalake")

  READ   (chiron media route / runs-detail serializer):
      url = await vault.get_download_url(asset_id, content_type=media_type)  # 302 → browser
      urls = await vault.get_download_urls([asset_id, ...])                  # batch for a drawer

The script saves real PNG/JPEG bytes, mints presigned GET URLs, fetches them over plain
HTTP (as a browser would), and asserts the bytes come back byte-identical with the right
Content-Type. It also proves split-horizon presigning (I/O endpoint != presign endpoint)
and prints a perf breakdown of the under-the-hood ops.

Run (in-process, default — uses the dev MinIO + keep-mongo directly):
    .venv-presign/bin/python scripts/presign_roundtrip_test.py

Run against a live DatalakeService (the real Chiron RPC path):
    .venv-presign/bin/python scripts/presign_roundtrip_test.py --remote http://localhost:18080
"""

from __future__ import annotations

import argparse
import asyncio
import io
import time
from contextlib import contextmanager

import httpx
from PIL import Image

from mindtrace.datalake import AsyncDatalake, AsyncDataVault
from mindtrace.registry import Mount, MountBackendKind, S3AccessKeyAuth, S3MountConfig

# ── dev infra (ds up) ────────────────────────────────────────────────────────
MINIO_IO_ENDPOINT = "localhost:29000"       # what the service uses for S3 I/O
MINIO_PRESIGN_ENDPOINT = "127.0.0.1:29000"  # what browsers get (split-horizon proof)
MONGO_URI = "mongodb://localhost:27020"
MONGO_DB = "mindtrace_presign_test"
BUCKET = "presign-test"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"


def _png_bytes(color: tuple[int, int, int], size=(160, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(color: tuple[int, int, int], size=(160, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@contextmanager
def timed(label: str, store: dict[str, float]):
    t0 = time.perf_counter()
    yield
    store[label] = (time.perf_counter() - t0) * 1000.0


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


async def build_inprocess_vault() -> tuple[AsyncDataVault, AsyncDatalake]:
    mount = Mount(
        name="minio",
        backend=MountBackendKind.S3,
        config=S3MountConfig(
            bucket=BUCKET,
            endpoint=MINIO_IO_ENDPOINT,
            secure=False,
            presign_endpoint=MINIO_PRESIGN_ENDPOINT,  # ← split horizon
            presign_secure=False,
        ),
        auth=S3AccessKeyAuth(access_key=ACCESS_KEY, secret_key=SECRET_KEY),
        is_default=True,
        registry_options={"mutable": True},
    )
    datalake = AsyncDatalake(
        mongo_db_uri=MONGO_URI,
        mongo_db_name=MONGO_DB,
        mounts=[mount],
        default_mount="minio",
    )
    await datalake.initialize()
    return AsyncDataVault(datalake), datalake


async def run(vault: AsyncDataVault, *, label: str, check_split: bool) -> None:
    print(f"\n=== {label} ===")
    perf: dict[str, float] = {}
    suffix = str(int(time.time() * 1000))

    # ── WRITE: exactly what the bridge does per captured POV ────────────────
    png = _png_bytes((220, 30, 30))
    jpg = _jpeg_bytes((30, 30, 220))

    with timed("save_png", perf):
        a_png = await vault.save(f"run-{suffix}/cam0", png, kind="image", media_type="image/png")
    a_jpg = await vault.save(f"run-{suffix}/cam1", jpg, kind="image", media_type="image/jpeg")
    _ok(f"saved 2 assets; reference asset_id = {a_png.asset_id}  media_type={a_png.media_type}")

    # ── READ (single): mint presigned URL, fetch as a browser would ─────────
    with timed("presign_single", perf):
        url = await vault.get_download_url(a_png.asset_id)
    assert url, "expected a presigned URL (got None — backend can't presign?)"
    _ok(f"presigned URL: {url.split('?')[0]}?…<sig>")

    if check_split:
        assert MINIO_PRESIGN_ENDPOINT.split(":")[0] in url, (
            f"presigned URL host should be the presign endpoint {MINIO_PRESIGN_ENDPOINT}, got {url}"
        )
        assert MINIO_IO_ENDPOINT.split(":")[0] + ":" + MINIO_IO_ENDPOINT.split(":")[1] not in url or \
            MINIO_PRESIGN_ENDPOINT != MINIO_IO_ENDPOINT
        _ok(f"split-horizon: URL signed for presign endpoint {MINIO_PRESIGN_ENDPOINT}, not I/O host")

    async with httpx.AsyncClient() as client:
        with timed("http_fetch", perf):
            resp = await client.get(url)
    assert resp.status_code == 200, f"GET {url} → {resp.status_code}: {resp.text[:200]}"
    assert resp.content == png, "fetched bytes differ from what was saved!"
    ctype = resp.headers.get("content-type")
    assert ctype == "image/png", f"expected Content-Type image/png, got {ctype!r}"
    _ok(f"fetched {len(resp.content)} bytes — byte-identical, Content-Type={ctype}")

    # jpeg too (different media_type must round-trip)
    jurl = await vault.get_download_url(a_jpg.asset_id)
    async with httpx.AsyncClient() as client:
        jresp = await client.get(jurl)
    assert jresp.content == jpg and jresp.headers.get("content-type") == "image/jpeg"
    _ok("jpeg asset: byte-identical, Content-Type=image/jpeg")

    # ── READ (batch): one call for many assets ──────────────────────────────
    ids = [a_png.asset_id, a_jpg.asset_id, "asset_does_not_exist"]
    with timed("presign_batch_3", perf):
        urls = await vault.get_download_urls(ids)
    assert set(urls) == {a_png.asset_id, a_jpg.asset_id}, f"unexpected batch keys: {set(urls)}"
    _ok(f"batch presign: {len(urls)}/{len(ids)} URLs (missing id correctly omitted)")

    # ── expiry sanity ───────────────────────────────────────────────────────
    assert "X-Amz-Expires" in url or "Expires" in url, "URL has no expiry param"
    _ok("URL carries an expiry parameter")

    print("  perf (ms):", {k: round(v, 2) for k, v in perf.items()})


async def perf_breakdown(vault: AsyncDataVault, datalake: AsyncDatalake, n: int = 20) -> None:
    """Show where time goes under the hood + batch vs N×single for a realistic fan-out."""
    print(f"\n=== perf breakdown (n={n} assets, in-process) ===")
    suffix = str(int(time.time() * 1000))
    assets = []
    for i in range(n):
        a = await vault.save(f"perf-{suffix}/cam{i}", _png_bytes((i * 7 % 255, 100, 150)),
                             kind="image", media_type="image/png")
        assets.append(a)
    ids = [a.asset_id for a in assets]

    # N× single
    t0 = time.perf_counter()
    for aid in ids:
        await vault.get_download_url(aid)
    loop_ms = (time.perf_counter() - t0) * 1000

    # one batch
    t0 = time.perf_counter()
    urls = await vault.get_download_urls(ids)
    batch_ms = (time.perf_counter() - t0) * 1000
    assert len(urls) == n

    # decompose a single op: mongo get_asset vs metadata-fetch+sign
    aid = ids[0]
    t0 = time.perf_counter()
    asset = await datalake.get_asset(aid)
    mongo_ms = (time.perf_counter() - t0) * 1000
    ref = asset.payload_storage_ref or asset.storage_ref
    t0 = time.perf_counter()
    await datalake.get_object_download_url(ref, response_content_type=asset.media_type)
    meta_sign_ms = (time.perf_counter() - t0) * 1000

    print(f"  single op total ≈ mongo_get_asset {mongo_ms:.2f}ms + (metadata_fetch+sign) {meta_sign_ms:.2f}ms")
    print(f"  {n}× single (looped) : {loop_ms:.1f} ms  ({loop_ms / n:.2f} ms/asset)")
    print(f"  1× batch({n})        : {batch_ms:.1f} ms  ({batch_ms / n:.2f} ms/asset)")
    print(f"  batch speedup        : {loop_ms / batch_ms:.1f}×")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", help="DatalakeService URL (RPC path); omit for in-process")
    ap.add_argument("--perf", action="store_true", help="run the perf breakdown")
    args = ap.parse_args()

    if args.remote:
        vault = AsyncDataVault.from_url(args.remote)
        await run(vault, label=f"REMOTE via {args.remote}", check_split=False)
    else:
        vault, datalake = await build_inprocess_vault()
        await run(vault, label="IN-PROCESS (storage→registry→datalake→vault)", check_split=True)
        if args.perf:
            await perf_breakdown(vault, datalake)
        await datalake.close()

    print("\nALL CHECKS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
