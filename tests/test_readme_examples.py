"""
Test all Python code examples from mindtrace-models README files.

Extracts every ```python ... ``` block from all 8 READMEs, classifies each as
runnable (self-contained with imports) or fragment (needs prior context), and
validates them:

- Runnable snippets: executed in an isolated namespace
- Fragments: at minimum compiled with compile() to verify syntax

Snippets requiring unavailable optional deps (transformers, peft, etc.) or
external services (WandB, MLflow servers) are skipped.
"""

from __future__ import annotations

import re
import sys
import textwrap
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# README paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PKG = REPO_ROOT / "mindtrace" / "models"

README_FILES: list[tuple[str, Path]] = [
    ("top-level", MODELS_PKG / "README.md"),
    ("architectures", MODELS_PKG / "mindtrace" / "models" / "architectures" / "README.md"),
    ("training", MODELS_PKG / "mindtrace" / "models" / "training" / "README.md"),
    ("tracking", MODELS_PKG / "mindtrace" / "models" / "tracking" / "README.md"),
    ("evaluation", MODELS_PKG / "mindtrace" / "models" / "evaluation" / "README.md"),
    ("lifecycle", MODELS_PKG / "mindtrace" / "models" / "lifecycle" / "README.md"),
    ("serving", MODELS_PKG / "mindtrace" / "models" / "serving" / "README.md"),
    ("archivers", MODELS_PKG / "mindtrace" / "models" / "archivers" / "README.md"),
]

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


@dataclass
class CodeBlock:
    readme: str
    index: int  # 0-based within that README
    code: str
    first_line: str = ""

    def __post_init__(self):
        lines = self.code.strip().splitlines()
        self.first_line = lines[0] if lines else ""

    @property
    def label(self) -> str:
        short = self.first_line[:60]
        return f"{self.readme}[{self.index}] {short}"


def extract_blocks() -> list[CodeBlock]:
    blocks: list[CodeBlock] = []
    for name, path in README_FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, m in enumerate(CODE_BLOCK_RE.finditer(text)):
            raw = textwrap.dedent(m.group(1))
            blocks.append(CodeBlock(readme=name, index=i, code=raw))
    return blocks


ALL_BLOCKS = extract_blocks()

# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------

_DEP_CACHE: dict[str, bool] = {}


def _dep_available(mod: str) -> bool:
    if mod not in _DEP_CACHE:
        try:
            __import__(mod)
            _DEP_CACHE[mod] = True
        except ImportError:
            _DEP_CACHE[mod] = False
    return _DEP_CACHE[mod]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Modules whose absence means the snippet should be skipped entirely.
OPTIONAL_DEP_MODULES = ["transformers", "peft"]

# Strings that indicate a snippet needs an external service, filesystem
# resource, or references undefined variables from prior context -- compile
# only, do not exec.
COMPILE_ONLY_MARKERS = [
    # External resources / services
    "from_pretrained(",
    "YOLO(",
    "SAM(",
    "YOLOWorld(",
    'model_path="model.onnx"',
    "onnx.load(",
    'torch.load(f"',
    "torch.onnx.export(",
    "yolo_model.train(",
    "hf_trainer.train()",
    "ts_inference_url=",
    "Tracker.from_config(",
    "registry.save(",
    "registry.load(",
    "registry = Registry(",
    "bridge.save(",
    "trainer.fit(",
    "trainer.train(",
    "runner.run(",
    "runner.evaluate(",
    "model.train(",
    'tracking_uri="http',
    "DatalakeDataset(",
    "build_datalake_loader(",
    "init_distributed(",
    "wrap_ddp(",
    "cleanup_distributed(",
    "card.save(",
    "ModelCard.load(",
    "exporter.export(",
    "model.backbone.merge_lora()",
    "model.backbone.save_pretrained(",
    "model.backbone.print_trainable_parameters()",
    # Prior-block variables -- snippets that reference model/card/opt/etc
    # from earlier code blocks in the same README section
    "model.backbone(",
    "model.head(",
    "model.backbone_info",
    "model(x)",
    "model(images)",
    "features = model",
    "logits   = model",
    "info     = model",
    "svc.input_names",
    "svc.output_names",
    "svc.input_shapes",
    "svc.output_shapes",
    "svc.info()",
    "combo.named_losses",
    "card.get_metric(",
    "card.summary()",
    "card.registry_key(",
    "card.to_dict()",
    "card3 = ModelCard.from_dict(",
    "card.add_result(",
    "r.to_dict()",
    "r2 = EvalResult.from_dict(",
    "results[",
    "report =",
    # Metric snippet fragments referencing `preds`, `targets` from context
    "acc = accuracy(preds",
    "top5 = top_k_accuracy(",
    "p, r, f1 = precision_recall_f1(",
    "cm = confusion_matrix(",
    "mAP = mean_average_precision(predictions",
    "coco = mean_average_precision_50_95(",
    "iou_matrix = box_iou(",
    "iou = mean_iou(preds",
    "dice = dice_score(preds",
    "pa = pixel_accuracy(preds",
    "mae_val = mae(preds",
    "mse_val = mse(preds",
    "rmse_val = rmse(preds",
    "r2 = r2_score(preds",
    # WandB / MLflow external service connections
    "WandBTracker(",
    "MLflowTracker(",
    "CompositeTracker(trackers=[",
    # Scheduler/optimizer needing prior `model`/`opt` variables
    "build_scheduler(",
    "WarmupCosineScheduler(",
    # Trainer-integrated blocks referencing prior model/loss/optimizer
    "Trainer(",
    "LRMonitor(",
    # Promote/demote referencing prior `card` and `registry`
    "promote(",
    "demote(",
    # build_optimizer referencing prior `model`
    "build_optimizer(",
    # head(features) referencing prior `features` variable
    "head(features)",
    # build_model used but not imported (context-dependent snippet)
    "build_model(",
]

# Backbones that need `transformers` package at runtime
_TRANSFORMERS_BACKBONES = [
    "dino_v2_small", "dino_v2_base", "dino_v2_large", "dino_v2_giant",
    "dino_v2_small_reg", "dino_v2_base_reg", "dino_v2_large_reg", "dino_v2_giant_reg",
    "dino_v3_small", "dino_v3_small_plus", "dino_v3_base", "dino_v3_large",
    "dino_v3_large_sat", "dino_v3_huge_plus", "dino_v3_7b", "dino_v3_7b_sat",
    "dino_v3_convnext_tiny", "dino_v3_convnext_small",
    "dino_v3_convnext_base", "dino_v3_convnext_large",
]


def _needs_transformers_backbone(code: str) -> bool:
    """Check if the snippet tries to build a backbone that requires transformers."""
    for name in _TRANSFORMERS_BACKBONES:
        if f'"{name}"' in code or f"'{name}'" in code:
            return True
    if "build_model_from_hf" in code:
        return True
    return False


def _has_marker(code: str, markers: list[str]) -> bool:
    return any(m in code for m in markers)


def _needs_unavailable_dep(code: str) -> str | None:
    """Return the name of an unavailable optional dep the snippet needs, or None."""
    for pkg in OPTIONAL_DEP_MODULES:
        if f"from {pkg}" in code or f"import {pkg}" in code:
            if not _dep_available(pkg):
                return pkg
    # Implicit transformers dependency via backbone names
    if _needs_transformers_backbone(code) and not _dep_available("transformers"):
        return "transformers (backbone)"
    return False


def _is_pure_import_block(code: str) -> bool:
    """True if the block is purely import statements (API reference listing)."""
    stripped = code.strip()
    if not stripped.startswith(("from ", "import ", "#")):
        return False
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    return all(
        l.startswith(("from ", "import ", ")", ",", "#"))
        or l.endswith(",")
        for l in lines
    )


def _uses_undefined_variable(code: str) -> bool:
    """Check if the code references a variable that is not defined within it.

    Specifically catches patterns where a snippet imports a function but then
    calls it with a variable (like `model`, `card`, `opt`, `features`) that
    was defined in a prior README block.
    """
    # Build set of names that appear in import statements
    imported_names: set[str] = set()
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("from ") and " import " in stripped:
            # Extract imported names
            after_import = stripped.split(" import ", 1)[1]
            for name in after_import.split(","):
                name = name.strip().rstrip(",").strip()
                if name and name != "(":
                    imported_names.add(name)
        elif stripped.startswith("import "):
            for name in stripped[7:].split(","):
                name = name.strip()
                if " as " in name:
                    name = name.split(" as ")[1].strip()
                if name:
                    imported_names.add(name)

    # Known context variables that come from prior blocks
    context_vars = {"model", "card", "registry", "opt", "features", "trainer",
                    "tracker", "optimizer", "loss_fn", "train_loader", "val_loader",
                    "hf_model", "classifier", "detector", "segmenter", "regressor",
                    "pred_mask", "true_mask", "pred_boxes", "true_boxes",
                    "metrics", "epoch"}

    # Check if the code references any of these without defining them
    for var in context_vars:
        # Simple check: var appears in code but not in left side of assignment
        # and not in import statements
        if var in imported_names:
            continue
        # Check if var is used (as a word boundary match)
        pattern = rf'\b{re.escape(var)}\b'
        if re.search(pattern, code):
            # Check it's not being defined (assigned to) in this block
            defined = False
            for line in code.splitlines():
                stripped = line.strip()
                if stripped.startswith(f"{var} =") or stripped.startswith(f"{var}:"):
                    defined = True
                    break
                if stripped.startswith(f"def ") and f"({var}" in stripped:
                    defined = True
                    break
            if not defined:
                return True
    return False


def classify_block(block: CodeBlock) -> str:
    """Return one of: 'run', 'compile_only', 'skip'."""
    code = block.code

    # Needs unavailable optional dep -- skip
    dep = _needs_unavailable_dep(code)
    if dep:
        return "skip"

    # Pure import/API reference blocks -- compile only
    if _is_pure_import_block(code):
        return "compile_only"

    # Needs network/files/running services or context from prior blocks
    if _has_marker(code, COMPILE_ONLY_MARKERS):
        return "compile_only"

    # Uses undefined variables from prior context
    if _uses_undefined_variable(code):
        return "compile_only"

    # If it has at least one import/from statement, try to run it
    if "import " in code or "from " in code:
        return "run"

    # Otherwise just compile
    return "compile_only"


# ---------------------------------------------------------------------------
# Test parametrization
# ---------------------------------------------------------------------------


def _block_id(block: CodeBlock) -> str:
    return f"{block.readme}_{block.index}"


@pytest.fixture(params=ALL_BLOCKS, ids=[_block_id(b) for b in ALL_BLOCKS])
def code_block(request):
    return request.param


class TestReadmeExamples:
    """Verify every Python code block in the mindtrace-models READMEs."""

    def test_code_block(self, code_block: CodeBlock):
        kind = classify_block(code_block)
        code = code_block.code

        if kind == "skip":
            dep = _needs_unavailable_dep(code)
            pytest.skip(f"requires unavailable optional dep: {dep}")

        if kind == "compile_only":
            try:
                compile(code, f"<{code_block.label}>", "exec")
            except SyntaxError as exc:
                pytest.fail(
                    f"SYNTAX ERROR in {code_block.label}:\n"
                    f"{exc}\n\n--- code ---\n{code}"
                )
            return

        # kind == "run"
        assert kind == "run"
        ns: dict[str, Any] = {}
        try:
            exec(compile(code, f"<{code_block.label}>", "exec"), ns)
        except Exception as exc:
            tb = traceback.format_exc()
            pytest.fail(
                f"RUNTIME ERROR in {code_block.label}:\n"
                f"{exc}\n\n--- traceback ---\n{tb}\n\n--- code ---\n{code}"
            )


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


def main():
    """Run all README code blocks and print a summary table."""
    blocks = extract_blocks()
    results: list[tuple[str, str, str, str]] = []
    passed = failed = skipped = 0
    bugs: list[tuple[str, str, str]] = []

    print(f"\nExtracted {len(blocks)} Python code blocks from {len(README_FILES)} READMEs\n")
    print(f"{'#':<4} {'README':<16} {'Kind':<14} {'Result':<12} First line")
    print("=" * 110)

    for i, block in enumerate(blocks):
        kind = classify_block(block)
        code = block.code

        if kind == "skip":
            dep = _needs_unavailable_dep(code)
            outcome = "SKIP"
            detail = dep or "optional dep"
            skipped += 1
        elif kind == "compile_only":
            try:
                compile(code, f"<{block.label}>", "exec")
                outcome = "PASS"
                detail = "compile"
                passed += 1
            except SyntaxError as exc:
                outcome = "FAIL"
                detail = f"syntax: {exc.msg}"
                failed += 1
                bugs.append((block.label, detail, code))
        else:  # run
            ns: dict[str, Any] = {}
            try:
                exec(compile(code, f"<{block.label}>", "exec"), ns)
                outcome = "PASS"
                detail = "exec"
                passed += 1
            except Exception as exc:
                outcome = "FAIL"
                detail = f"{type(exc).__name__}: {str(exc)[:80]}"
                failed += 1
                bugs.append((block.label, f"{type(exc).__name__}: {exc}", code))

        short = block.first_line[:50]
        print(f"{i:<4} {block.readme:<16} {kind:<14} {outcome:<12} {short}")
        results.append((block.label, kind, outcome, detail))

    print("=" * 110)
    print(f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped, {len(blocks)} total\n")

    if bugs:
        print("=" * 110)
        print("DOCUMENTATION BUGS FOUND")
        print("=" * 110)
        for label, error, code in bugs:
            print(f"\n--- {label} ---")
            print(f"Error: {error}")
            print(f"Code:\n{textwrap.indent(code.strip(), '  ')}")
            print()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
