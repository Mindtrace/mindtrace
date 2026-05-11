# Image Quality Analyzer

Scans a folder of images (recursively) to detect **blur** and **darkness**. Each image first passes through fast deterministic checks; only images that breach a threshold are sent to a VLM for confirmation. Two Ollama instances run in Docker for parallel analysis.

## How it works

```
image
  │
  ├─► Laplacian variance  ──── above threshold ──► OK (skip VLM)
  │   (blur check)
  │
  └─► Mean luma           ──── above threshold ──► OK (skip VLM)
      (darkness check)
              │
              └─► below either threshold ──► VLM agent ──► "ok" | "blur" | "dark"
```

Results are saved incrementally — if the script is interrupted, re-running it resumes from where it left off.

---

## Prerequisites

- Docker + Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- NVIDIA GPU recommended (remove the `deploy` sections from `docker-compose.yml` for CPU-only)

---

## Setup

### 1. Start Ollama containers

From this directory:

```bash
docker compose up -d
```

This starts two Ollama instances:
- `ollama1` → `http://localhost:11436`
- `ollama2` → `http://localhost:11435`

### 2. Pull the vision model into both instances

```bash
./pull_models.sh             # defaults to gemma4:latest
./pull_models.sh llava:7b    # or specify a different model
```

### 3. Install Python dependencies

From this directory:

```bash
uv sync
```

---

## Configuration

Edit `config.yaml` before running:

```yaml
folder_path: "/path/to/your/images"   # folder to scan (subfolders included)

ollama_urls:
  - "http://localhost:11436"
  - "http://localhost:11435"

model: "gemma4:latest"      # must match what you pulled in step 2

blur_threshold: 100.0       # Laplacian variance — below this triggers VLM
darkness_threshold: 50.0    # Mean luma (0–255) — below this triggers VLM

workers: 2                  # parallel workers, one per Ollama instance
state_file: "analysis_state.json"   # progress checkpoint
output_file: "flagged_images.json"  # final results
```

**Tuning thresholds:**
- Increase `blur_threshold` (e.g. `200`) to catch more borderline blur cases.
- Increase `darkness_threshold` (e.g. `80`) to catch more dimly lit images.
- The VLM acts as a second opinion — deterministic flags alone do not mark an image as bad.

---

## Running

```bash
uv run python analyze.py

# Override the folder without editing config.yaml
uv run python analyze.py --folder /my/images

# Use a different config file
uv run python analyze.py --config /my/config.yaml
```

### Example output

```
Images found: 1240 | Already analyzed: 0 | Pending: 1240
Analyzing: 100%|████████████████| 1240/1240 [04:12<00:00,  4.91 img/s]
  FLAGGED [blur] /images/run3/frame_0042.jpg
  FLAGGED [dark] /images/run5/frame_0017.png

Complete. 2 flagged image(s) → flagged_images.json
```

---

## Resuming after interruption

Press `Ctrl+C` at any time. In-flight images finish before the script exits. Progress is saved to `analysis_state.json` after each image. Re-run the same command to continue from where it stopped.

To start a completely fresh analysis, delete the state file:

```bash
rm analysis_state.json
```

---

## Output files

**`flagged_images.json`** — list of problematic images with details:

```json
{
  "flagged_images": ["/images/frame_0042.jpg"],
  "details": [
    {
      "path": "/images/frame_0042.jpg",
      "blur_variance": 18.4,
      "mean_luma": 112.3,
      "deterministic_flags": ["blur"],
      "vlm_category": "blur",
      "vlm_description": "Image is out of focus — edges are not resolvable.",
      "flagged": true
    }
  ]
}
```

**`analysis_state.json`** — full per-image results including images that passed (used for resume).

---

## Stopping Ollama

```bash
docker compose down
```

To also remove the downloaded model data:

```bash
docker compose down -v
```
