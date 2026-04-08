"""Unit tests for `mindtrace.models.training.losses.composite`."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
nn = pytest.importorskip("torch.nn")

from mindtrace.models.training.losses.composite import ComboLoss  # noqa: E402


class ConstantLoss(nn.Module):
    def __init__(self, value: float):
        super().__init__()
        self.value = value

    def forward(self, *args, **kwargs):
        return torch.tensor(self.value, dtype=torch.float32)


class TestComboLoss:
    def test_accepts_list_of_losses_and_auto_names_them(self):
        combo = ComboLoss(losses=[ConstantLoss(1.0), ConstantLoss(2.0)], weights=[0.5, 2.0])

        loss = combo(torch.tensor([1.0]))

        assert loss.item() == pytest.approx(4.5)
        assert combo.named_losses == {"loss_0": 0.5, "loss_1": 4.0}

    def test_weights_list_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="weights list length"):
            ComboLoss(losses={"a": ConstantLoss(1.0), "b": ConstantLoss(2.0)}, weights=[1.0])

    def test_invalid_weights_type_raises(self):
        with pytest.raises(TypeError, match="weights must be dict, list, or None"):
            ComboLoss(losses={"a": ConstantLoss(1.0)}, weights="bad")  # type: ignore[arg-type]

    def test_extra_repr_lists_weights(self):
        combo = ComboLoss(losses={"dice": ConstantLoss(1.0), "ce": ConstantLoss(2.0)}, weights={"dice": 0.5, "ce": 1.5})

        assert combo.extra_repr() == "weights={dice=0.5, ce=1.5}"
