# Pruning

> Make a model smaller and faster by removing the parts that contribute little.

## The idea in plain terms

A trained network is almost always **over-parameterized** — it has far more weights and channels than it strictly needs, and many of them contribute almost nothing to the output. **Pruning** removes them.

**Analogy:** pruning a plant. You cut the branches that aren't bearing fruit so the plant puts its energy into the ones that are — and the whole thing ends up smaller and lighter. Same here: strip the near-dead weights and (after a short recovery) the network is smaller and faster while predicting almost the same.

Where quantization keeps every number but stores each one with less precision, **pruning keeps full precision but has fewer numbers**. They compose well — prune first, then quantize.

## Structured vs unstructured — the distinction that matters

This is the one thing to understand about pruning: **not all pruning makes a model faster.**

| Kind | What it removes | Actually faster? |
|------|-----------------|:----------------:|
| **Structured (channel)** | Whole channels / filters — the tensor physically shrinks | **Yes, on any hardware** |
| **Unstructured (magnitude)** | Individual weights, set to zero | Smaller in theory, but **no speedup** unless the hardware/runtime exploits sparsity |
| **2:4 semi-structured** | Exactly 2 of every 4 weights, zeroed in a fixed pattern | **Yes, on NVIDIA Ampere+ GPUs** (sparse tensor cores) |

### Structured channel pruning — the one that speeds things up

Removes whole channels and — crucially — propagates the change through the network (the next layer's inputs, skip connections, batch-norm) so you get a genuinely smaller architecture that runs faster everywhere.

```python
from mindtrace.models.optimization import ChannelPruner
import torch

pruner = ChannelPruner(sparsity=0.4, ignore=["head"], example_input=torch.randn(1, 3, 224, 224))
slim_model = pruner.run(model)
print(pruner.summary())   # params_before/after, flops_before/after
```

Pruning drops accuracy immediately, so you almost always **fine-tune for a few epochs afterward** to recover it (the network re-learns without the removed capacity).

### Gradual pruning during training

Pruning 50% in one shot hurts more than pruning gradually. `PruningSchedule` ramps the sparsity up over several epochs *while training*, so accuracy heals between steps.

```python
from mindtrace.models.optimization import PruningSchedule
from mindtrace.models.training import Trainer

schedule = PruningSchedule(final_sparsity=0.5, start_epoch=1, end_epoch=10)
trainer = Trainer(model=model, loss_fn=loss, optimizer=opt, callbacks=[schedule])
trainer.fit(train_loader, val_loader, epochs=14)
```

### 2:4 sparsity for Ampere GPUs

```python
from mindtrace.models.optimization import to_sparse_24, sparsity

model = to_sparse_24(model)   # 2 of every 4 weights zeroed
print(sparsity(model))        # ~0.5
```

`sparsity(model)` is a diagnostic: the fraction of weights that are exactly zero.

## Honest notes

- **Unstructured pruning is mostly a research tool here** — it shrinks the number of non-zero weights but won't make inference faster on ordinary hardware. Reach for **structured** pruning for real edge speedups.
- Always fine-tune after pruning, and re-check accuracy with the [runner's gates](../README.md).

See the [optimization overview](../README.md) for combining pruning with quantization in one recipe.
