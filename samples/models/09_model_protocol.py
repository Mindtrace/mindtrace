"""Task-level local inference with Model and TorchModel.

Requires the transformers extra and downloads the selected Hugging Face model
and processor on first use.
"""

from pathlib import Path
from typing import Any

import torch
from PIL import Image

from mindtrace.models import (
    ClassificationPostprocessor,
    HuggingFaceImageProcessor,
    Model,
    TorchModel,
    build_model_from_hf,
)

MODEL_ID = "microsoft/swin-tiny-patch4-window7-224"
LABELS = ["airplane", "automobile", "bird"]
IMAGE_PATH = Path(__file__).resolve().parents[2] / "tests" / "resources" / "hopper.png"


class ImageSizeModel:
    """A structural Model implementation with no Mindtrace base class."""

    def predict(self, inputs: Image.Image, **params: Any) -> dict[str, Any]:
        return {"size": inputs.size, "params": params}


image = Image.open(IMAGE_PATH).convert("RGB")

# Any class with a compatible predict method satisfies the Model protocol.
structural_model: Model[Image.Image, dict[str, Any]] = ImageSizeModel()
print(structural_model.predict(image, source="local"))

network = build_model_from_hf(
    MODEL_ID,
    head="linear",
    num_classes=len(LABELS),
)
model = TorchModel(
    network=network,
    processor=HuggingFaceImageProcessor(MODEL_ID),
    postprocessor=ClassificationPostprocessor(labels=LABELS),
    device="auto",
)

# predict owns processing, inference mode, device placement, and postprocessing.
for prediction in model.predict(image, include_probabilities=True):
    print(prediction.to_dict())

# Calling the module directly retains standard tensor-to-tensor semantics.
model.eval()
with torch.inference_mode():
    preprocessed_batch = model.processor(image).to(model.device)
    logits = model(preprocessed_batch)
print(f"Raw logits shape: {tuple(logits.shape)}")

# Floating-point CHW and BCHW tensors are treated as already preprocessed.
for prediction in model.predict(preprocessed_batch):
    print(prediction.to_dict())
