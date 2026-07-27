"""Declarative optimization recipes.

An :class:`OptimizationRecipe` is a serializable, ordered pipeline of
optimization steps (prune, finetune, quantize, export, compile).  Each step is
a small pydantic model discriminated by its ``op`` field, so recipes
round-trip losslessly through JSON and can be stored next to model artifacts,
versioned, and replayed by the
:class:`~mindtrace.models.optimization.runner.OptimizationRunner`.

Example::

    recipe = OptimizationRecipe(
        name="cnn-int8-edge",
        steps=[
            Prune(method="structured_channel", sparsity=0.5, ignore=["head"]),
            Finetune(epochs=3, lr=1e-4),
            Export(opset=17),
            Quantize(mode="static_ptq", samples=512),
            Compile(target="intel-cpu-openvino"),
        ],
    )
    recipe.save("recipe.json")
    same = OptimizationRecipe.load("recipe.json")
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

__all__ = [
    "Compile",
    "Export",
    "Finetune",
    "OptimizationRecipe",
    "Prune",
    "QAT",
    "Quantize",
    "RecipeStep",
]


class Prune(BaseModel):
    """Pruning step (torch domain).

    Attributes:
        op: Discriminator, always ``"prune"``.
        method: ``"structured_channel"`` for physical channel removal via
            :class:`~mindtrace.models.optimization.prune.ChannelPruner`, or
            ``"magnitude"`` for global unstructured magnitude pruning.
        sparsity: Fraction of channels/weights to remove, in ``(0, 1)``.
        ignore: Module-name prefixes that must never be pruned.
    """

    op: Literal["prune"] = "prune"
    method: Literal["structured_channel", "magnitude"] = "structured_channel"
    sparsity: float = Field(default=0.5, gt=0.0, lt=1.0)
    ignore: list[str] | None = None


class Finetune(BaseModel):
    """Finetuning step (torch domain), used to recover accuracy after pruning.

    Attributes:
        op: Discriminator, always ``"finetune"``.
        epochs: Number of training epochs.
        lr: Learning rate for the (default AdamW) optimizer.
    """

    op: Literal["finetune"] = "finetune"
    epochs: int = Field(default=1, ge=1)
    lr: float = Field(default=1e-4, gt=0.0)


class QAT(BaseModel):
    """Quantization-aware training step (torch domain, transformer-capable).

    Inserts module-level fake-quant (:func:`~mindtrace.models.optimization.prepare_qat`),
    trains so the weights adapt to INT8 rounding, then converts to a scheme-preserving
    INT8 model (:func:`~mindtrace.models.optimization.convert_qat`). Unlike static PTQ
    (onnx domain), QAT operates on the live torch model, so it must precede any Export
    step — and the runner's accuracy gate wraps it like any other lossy step.

    Attributes:
        op: Discriminator, always ``"qat"``.
        epochs: Training epochs to adapt to quantization.
        lr: Learning rate for the (default AdamW) optimizer.
        weight_bits: Weight bit-width (2–8).
        activation_bits: Activation bit-width; ``0`` = weight-only.
        weight_per_channel: Per-output-channel weight scales.
    """

    op: Literal["qat"] = "qat"
    epochs: int = Field(default=1, ge=1)
    lr: float = Field(default=1e-4, gt=0.0)
    weight_bits: int = Field(default=8, ge=2, le=8)
    activation_bits: int = Field(default=8, ge=0, le=8)
    weight_per_channel: bool = True


class Quantize(BaseModel):
    """Quantization step (onnx domain).

    Attributes:
        op: Discriminator, always ``"quantize"``.
        mode: ``"static_ptq"`` (weights + activations, needs calibration
            data) or ``"dynamic"`` (weights only, no calibration).
        precision: Quantization precision (``"int8"`` or ``"uint8"``).
        samples: Maximum number of calibration samples (static PTQ only).
        per_channel: Quantize weights per output channel (static PTQ only).
        calibration_method: Activation range estimator — ``"minmax"``,
            ``"entropy"`` or ``"percentile"`` (static PTQ only).
    """

    op: Literal["quantize"] = "quantize"
    mode: Literal["static_ptq", "dynamic"] = "static_ptq"
    precision: str = "int8"
    samples: int = Field(default=512, ge=1)
    per_channel: bool = True
    calibration_method: str = "minmax"


class Export(BaseModel):
    """ONNX export step; switches the pipeline from torch to onnx domain.

    Attributes:
        op: Discriminator, always ``"export"``.
        opset: ONNX opset version to target.
        static_shape: Full input shape (including batch dimension) used to
            build the tracing input.  When ``None`` the runner infers it from
            one evaluation/calibration batch.
        simplify: Simplify the exported graph with ``onnxsim``.
        check: Verify numerical parity against PyTorch with ONNX Runtime.
    """

    op: Literal["export"] = "export"
    opset: int = Field(default=17, ge=7)
    static_shape: tuple[int, ...] | None = None
    simplify: bool = True
    check: bool = True


class Compile(BaseModel):
    """Compilation step (onnx domain): build a target-runtime artifact.

    Attributes:
        op: Discriminator, always ``"compile"``.
        target: Name of a registered deployment target (see
            :func:`~mindtrace.models.optimization.targets.list_targets`).
    """

    op: Literal["compile"] = "compile"
    target: str


RecipeStep = Annotated[Union[Prune, Finetune, QAT, Quantize, Export, Compile], Field(discriminator="op")]
"""Discriminated union of all recipe step types, keyed on ``op``."""


class OptimizationRecipe(BaseModel):
    """Ordered, serializable pipeline of optimization steps.

    Attributes:
        name: Human-readable recipe name (free-form, may be empty).
        steps: Ordered list of steps.  Validation is strict: an unknown
            ``op`` value raises a pydantic ``ValidationError``.

    Example::

        recipe = OptimizationRecipe(steps=[Export(), Quantize(mode="dynamic")])
        clone = OptimizationRecipe.from_json(recipe.to_json())
    """

    name: str = ""
    steps: list[RecipeStep] = Field(default_factory=list)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the recipe to a JSON string.

        Args:
            indent: Indentation passed to the JSON encoder (``None`` for
                compact output).

        Returns:
            JSON representation that :meth:`from_json` can round-trip.
        """
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, data: str | bytes) -> "OptimizationRecipe":
        """Deserialize a recipe from a JSON string.

        Args:
            data: JSON produced by :meth:`to_json` (or hand-written).

        Returns:
            The reconstructed :class:`OptimizationRecipe`.

        Raises:
            pydantic.ValidationError: If the JSON is malformed or contains an
                unknown step ``op``.
        """
        return cls.model_validate_json(data)

    def save(self, path: str | Path) -> Path:
        """Write the recipe as JSON to *path*.

        Args:
            path: Destination file path.  Parent directories are created as
                needed.

        Returns:
            The written path as a :class:`pathlib.Path`.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "OptimizationRecipe":
        """Read a recipe from a JSON file written by :meth:`save`.

        Args:
            path: Path to the JSON recipe file.

        Returns:
            The reconstructed :class:`OptimizationRecipe`.

        Raises:
            FileNotFoundError: If *path* does not exist.
            pydantic.ValidationError: If the file contents are invalid.
        """
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
