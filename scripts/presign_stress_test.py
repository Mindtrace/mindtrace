"""Presigned-download STRESS test with real camera images — mirrors the Chiron path.

Saves N real Basler JPEGs to the datalake (like a batch of captured POVs), then
hammers the presign + fetch path the way the Runs UI would:

  1. save N assets                          (vault.save → asset_id reference)
  2. single presign latency distribution    (vault.get_download_url, p50/p95)
  3. integrity check                         (fetch one URL, bytes == source file)
  4. batch presign scaling                   (vault.get_download_urls for 1/10/25/N)
     vs N× looped single                     (proves the batched-metadata win)
  5. concurrent fetch of all N URLs          (browser drawer loading N images)

Run against the isolated ds-dev datalake:
    .venv-presign/bin/python scripts/presign_stress_test.py \
        --remote http://localhost:18080 \
        --images-dir /home/can/dev/hackathon/mip_recent/eval_cache/ee796690-c84d-47d7-847b-be934dc79812 \
        --n 50
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import statistics
import time

import httpx

from mindtrace.datalake import AsyncDataVault

DEFAULT_IMAGES = "/home/can/dev/hackathon/mip_recent/eval_cache/ee796690-c84d-47d7-847b-be934dc79812"


def load_images(images_dir: str) -> list[tuple[str, bytes]]:
    paths = sorted(glob.glob(os.path.join(images_dir, "*.jpg")) + glob.glob(os.path.join(images_dir, "*.png")))
    if not paths:
        raise SystemExit(f"no images found in {images_dir}")
    out = []
    for p in paths:
        with open(p, "rb") as f:
            out.append((os.path.basename(p), f.read()))
    return out


def _media_type(name: str) -> str:
    return "image/png" if name.lower().endswith(".png") else "image/jpeg"


def pctl(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1)))))
    return xs[k]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--remote", default="http://localhost:18080")
    ap.add_argument("--images-dir", default=DEFAULT_IMAGES)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--fetch-concurrency", type=int, default=16)
    args = ap.parse_args()

    imgs = load_images(args.images_dir)
    print(f"loaded {len(imgs)} real images from {args.images_dir} "
          f"(avg {statistics.mean(len(b) for _, b in imgs) / 1024:.0f} KiB)")

    vault = AsyncDataVault.from_url(args.remote)
    run = str(int(time.time() * 1000))

    # ── 1) save N assets (one per simulated capture) ────────────────────────
    print(f"\n[1] saving {args.n} assets …")
    asset_ids: list[str] = []
    src_by_id: dict[str, bytes] = {}
    ct_by_id: dict[str, str] = {}
    t0 = time.perf_counter()
    total_bytes = 0
    for i in range(args.n):
        name, data = imgs[i % len(imgs)]
        ct = _media_type(name)
        a = await vault.save(f"stress-{run}/img{i:03d}", data, kind="image", media_type=ct)
        asset_ids.append(a.asset_id)
        src_by_id[a.asset_id] = data
        ct_by_id[a.asset_id] = ct
        total_bytes += len(data)
    save_s = time.perf_counter() - t0
    print(f"    saved {args.n} assets, {total_bytes / 1e6:.1f} MB in {save_s:.1f}s "
          f"({total_bytes / 1e6 / save_s:.1f} MB/s, {save_s / args.n * 1000:.0f} ms/asset)")

    # ── 2) single-presign latency distribution ──────────────────────────────
    print("\n[2] single presign latency (vault.get_download_url) …")
    lat = []
    for aid in asset_ids:
        t = time.perf_counter()
        url = await vault.get_download_url(aid, content_type=ct_by_id[aid])
        lat.append((time.perf_counter() - t) * 1000)
        assert url, f"no URL for {aid}"
    print(f"    n={len(lat)}  min={min(lat):.1f}  p50={pctl(lat,50):.1f}  "
          f"p95={pctl(lat,95):.1f}  max={max(lat):.1f}  mean={statistics.mean(lat):.1f}  (ms)")

    # ── 3) integrity: fetch one URL, compare to source ──────────────────────
    print("\n[3] integrity check (fetch via presigned URL) …")
    aid0 = asset_ids[0]
    url0 = await vault.get_download_url(aid0, content_type=ct_by_id[aid0])
    async with httpx.AsyncClient() as c:
        r = await c.get(url0)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
    assert r.content == src_by_id[aid0], "fetched bytes != source file!"
    assert r.headers.get("content-type") == ct_by_id[aid0], r.headers.get("content-type")
    print(f"    ✓ {len(r.content)/1e6:.2f} MB byte-identical, Content-Type={r.headers.get('content-type')}")

    # ── 4) batch presign scaling vs looped single ───────────────────────────
    print("\n[4] batch presign vs N× single …")
    for size in sorted({1, 10, 25, args.n}):
        if size > args.n:
            continue
        ids = asset_ids[:size]
        t = time.perf_counter()
        urls = await vault.get_download_urls(ids)
        batch_ms = (time.perf_counter() - t) * 1000
        assert len(urls) == size, f"batch returned {len(urls)} for {size}"
        print(f"    batch({size:3d}) : {batch_ms:7.1f} ms total  ({batch_ms/size:5.2f} ms/asset)")

    t = time.perf_counter()
    for aid in asset_ids:
        await vault.get_download_url(aid)
    loop_ms = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    urls_all = await vault.get_download_urls(asset_ids)
    batch_all_ms = (time.perf_counter() - t) * 1000
    print(f"    {args.n}× looped single : {loop_ms:7.1f} ms ({loop_ms/args.n:.2f} ms/asset)")
    print(f"    1× batch({args.n})       : {batch_all_ms:7.1f} ms ({batch_all_ms/args.n:.2f} ms/asset)")
    print(f"    → batch speedup        : {loop_ms / batch_all_ms:.1f}×")

    # ── 5) concurrent fetch of all N (UI drawer load) ───────────────────────
    print(f"\n[5] concurrent fetch of all {args.n} images (sim. UI drawer, "
          f"concurrency={args.fetch_concurrency}) …")
    sem = asyncio.Semaphore(args.fetch_concurrency)
    fetched = {"ok": 0, "bytes": 0, "bad": 0}

    async def fetch(client: httpx.AsyncClient, aid: str, url: str) -> None:
        async with sem:
            r = await client.get(url)
        if r.status_code == 200 and r.content == src_by_id[aid]:
            fetched["ok"] += 1
            fetched["bytes"] += len(r.content)
        else:
            fetched["bad"] += 1

    t = time.perf_counter()
    async with httpx.AsyncClient(timeout=30) as client:
        await asyncio.gather(*(fetch(client, aid, urls_all[aid]) for aid in asset_ids))
    fetch_s = time.perf_counter() - t
    print(f"    fetched {fetched['ok']}/{args.n} OK ({fetched['bad']} bad), "
          f"{fetched['bytes']/1e6:.1f} MB in {fetch_s:.2f}s "
          f"({fetched['bytes']/1e6/fetch_s:.1f} MB/s)")
    assert fetched["bad"] == 0 and fetched["ok"] == args.n, "some fetches failed/mismatched"

    print("\nSTRESS TEST PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
