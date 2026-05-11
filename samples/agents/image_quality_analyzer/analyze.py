"""Image quality analyzer — deterministic blur/darkness checks + optional VLM confirmation."""

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
import yaml
from tqdm import tqdm

from mindtrace.agents import MindtraceAgent, OllamaProvider, OpenAIChatModel
from mindtrace.agents.prompts import BinaryContent

# ── Constants ──────────────────────────────────────────────────────────────────

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

SYSTEM_PROMPT = (
    "You are an image quality inspector.\n"
    "You will receive a single image. Judge whether it is usable for automated visual inspection.\n\n"
    "Categories:\n"
    '- "blur"  : image is out of focus or motion-blurred — fine details are not resolvable\n'
    '- "dark"  : image is too underexposed — important content is not discernible\n'
    '- "ok"    : image is clear and well-exposed enough for automated analysis\n\n'
    "An image that is naturally dark but where content is still discernible should be 'ok', not 'dark'.\n"
    'Return ONLY a JSON object: {"category": "ok"|"blur"|"dark", "description": "brief reason"}\n'
    "No markdown, no extra text."
)

_VALID_CATEGORIES = {"ok", "blur", "dark"}

# ── Shutdown / state ───────────────────────────────────────────────────────────

_shutdown = threading.Event()
_state_lock = threading.Lock()
_state: dict[str, dict] = {}
_state_file: Path = Path("analysis_state.json")


def _handle_shutdown(signum, frame):
    tqdm.write("\nInterrupt received — finishing in-flight work then exiting.")
    _shutdown.set()


def load_state(path: Path) -> dict[str, dict]:
    global _state, _state_file
    _state_file = path
    if path.exists():
        with open(path) as f:
            _state = json.load(f)
    return _state


def _persist_entry(key: str, result: dict) -> None:
    with _state_lock:
        _state[key] = result
        tmp = _state_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(_state, f, indent=2)
        tmp.replace(_state_file)


# ── Image discovery ────────────────────────────────────────────────────────────

def discover_images(folder: Path) -> list[Path]:
    images = []
    for root, _, files in os.walk(folder):
        for fname in sorted(files):
            if Path(fname).suffix.lower() in IMAGE_EXTENSIONS:
                images.append(Path(root) / fname)
    return sorted(images)


# ── Deterministic checks ───────────────────────────────────────────────────────

def check_blur(path: Path, threshold: float) -> tuple[bool, float]:
    """Laplacian variance — low variance means blurry."""
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True, 0.0
    variance = float(cv2.Laplacian(img, cv2.CV_64F).var())
    return variance < threshold, round(variance, 2)


def check_darkness(path: Path, threshold: float) -> tuple[bool, float]:
    """Mean luma — low mean means dark."""
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return True, 0.0
    mean_luma = float(np.mean(img))
    return mean_luma < threshold, round(mean_luma, 2)


# ── VLM agent ──────────────────────────────────────────────────────────────────

_agent_cache: dict[str, MindtraceAgent] = {}
_agent_lock = threading.Lock()


def _get_agent(ollama_url: str, model: str) -> MindtraceAgent:
    key = f"{ollama_url}:{model}"
    with _agent_lock:
        if key not in _agent_cache:
            provider = OllamaProvider(base_url=f"{ollama_url}/v1")
            mdl = OpenAIChatModel(model, provider=provider)
            _agent_cache[key] = MindtraceAgent(
                model=mdl,
                tools=[],
                system_prompt=SYSTEM_PROMPT,
                name="image_quality_agent",
            )
    return _agent_cache[key]


def _parse_vlm(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            cat = data.get("category", "")
            if cat not in _VALID_CATEGORIES:
                cat = "processing_error"
            return {"category": cat, "description": str(data.get("description", raw))[:500]}
        except json.JSONDecodeError:
            pass
    return {"category": "processing_error", "description": raw[:300]}


def run_vlm(path: Path, ollama_url: str, model: str, retries: int = 2) -> dict:
    agent = _get_agent(ollama_url, model)
    suffix = path.suffix.lower()
    media_type = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.lstrip('.')}"
    img_bytes = path.read_bytes()

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            raw = str(asyncio.run(agent.run(
                [BinaryContent(data=img_bytes, media_type=media_type)],
                deps=None,
                model_settings={"temperature": 0},
            )))
            return _parse_vlm(raw)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(3.0)
    return {"category": "processing_error", "description": str(last_exc)[:300]}


# ── Per-image worker ───────────────────────────────────────────────────────────

def analyze_image(
    path: Path,
    ollama_url: str,
    model: str,
    blur_threshold: float,
    darkness_threshold: float,
) -> dict:
    key = str(path)

    with _state_lock:
        if key in _state:
            return _state[key]

    result: dict = {
        "path": key,
        "blur_variance": None,
        "mean_luma": None,
        "deterministic_flags": [],
        "vlm_category": None,
        "vlm_description": None,
        "flagged": False,
    }

    try:
        is_blurry, variance = check_blur(path, blur_threshold)
        is_dark, luma = check_darkness(path, darkness_threshold)

        result["blur_variance"] = variance
        result["mean_luma"] = luma

        flags = []
        if is_blurry:
            flags.append("blur")
        if is_dark:
            flags.append("dark")
        result["deterministic_flags"] = flags

        if flags and not _shutdown.is_set():
            vlm = run_vlm(path, ollama_url, model)
            result["vlm_category"] = vlm["category"]
            result["vlm_description"] = vlm["description"]
            result["flagged"] = vlm["category"] in {"blur", "dark"}
        else:
            result["vlm_category"] = "skipped" if not flags else "shutdown"
            result["flagged"] = False

    except Exception as exc:
        result["vlm_category"] = "error"
        result["vlm_description"] = str(exc)[:300]
        result["flagged"] = True  # flag errors for manual review

    _persist_entry(key, result)
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Detect blurry and dark images using deterministic checks + VLM.")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML (default: config.yaml)")
    parser.add_argument("--folder", help="Override folder_path from config")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    folder = Path(args.folder or cfg["folder_path"])
    ollama_urls: list[str] = cfg["ollama_urls"]
    model: str = cfg.get("model", "gemma3:4b")
    blur_threshold: float = float(cfg.get("blur_threshold", 100.0))
    darkness_threshold: float = float(cfg.get("darkness_threshold", 50.0))
    workers: int = int(cfg.get("workers", 2))
    state_file = Path(cfg.get("state_file", "analysis_state.json"))
    output_file = Path(cfg.get("output_file", "flagged_images.json"))

    if not folder.is_dir():
        print(f"Folder not found: {folder}")
        sys.exit(1)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    state = load_state(state_file)
    all_images = discover_images(folder)
    pending = [img for img in all_images if str(img) not in state]

    already_flagged = [v for v in state.values() if v.get("flagged")]
    print(
        f"Images found: {len(all_images)} | "
        f"Already analyzed: {len(state)} | "
        f"Pending: {len(pending)}"
    )

    new_flagged: list[dict] = []

    if pending and not _shutdown.is_set():
        # Round-robin across available Ollama URLs
        url_cycle = [ollama_urls[i % len(ollama_urls)] for i in range(len(pending))]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(analyze_image, img, url, model, blur_threshold, darkness_threshold): img
                for img, url in zip(pending, url_cycle)
            }

            with tqdm(total=len(pending), desc="Analyzing", unit="img", dynamic_ncols=True) as pbar:
                for future in as_completed(futures):
                    if _shutdown.is_set():
                        for f in futures:
                            f.cancel()
                        break
                    img = futures[future]
                    try:
                        result = future.result()
                        if result.get("flagged"):
                            new_flagged.append(result)
                            tqdm.write(f"  FLAGGED [{result['vlm_category']}] {img}")
                    except Exception as exc:
                        tqdm.write(f"  ERROR {img}: {exc}")
                    pbar.update(1)

    all_flagged = already_flagged + new_flagged
    flagged_paths = [r["path"] for r in all_flagged]

    with open(output_file, "w") as f:
        json.dump({"flagged_images": flagged_paths, "details": all_flagged}, f, indent=2)

    print(f"\nComplete. {len(all_flagged)} flagged image(s) → {output_file}")
    if flagged_paths:
        print("\nFlagged images:")
        for p in flagged_paths:
            print(f"  {p}")


if __name__ == "__main__":
    main()
