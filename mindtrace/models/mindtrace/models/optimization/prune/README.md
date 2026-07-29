# Pruning

Shrink and speed up a model by removing the parameters that contribute little. A trained network is typically over-parameterized: many weights and channels barely affect the output. Pruning removes them, and after a short recovery phase the network is smaller and faster with almost the same predictions.

Where quantization keeps every number but stores each at lower precision, pruning keeps full precision but has fewer numbers. The two compose well: prune first, then quantize.

## Structured vs unstructured

Not all pruning makes a model faster. This is the distinction that matters:

| Kind | What it removes | Faster? |
|------|-----------------|:-------:|
| Structured (channel) | Whole channels / filters; the tensor physically shrinks | Yes, on any hardware |
| Unstructured (magnitude) | Individual weights, set to zero | Smaller in theory, no speedup unless the runtime exploits sparsity |
| 2:4 semi-structured | 2 of every 4 weights, zeroed in a fixed pattern | Yes, on NVIDIA Ampere+ (sparse tensor cores) |

### Structured channel pruning

Removes whole channels and propagates the change through the network (the next layer's inputs, skip connections, batch-norm), producing a genuinely smaller architecture that runs faster everywhere.

```python
from mindtrace.models.optimization import ChannelPruner
import torch

pruner = ChannelPruner(sparsity=0.4, ignore=["head"], example_input=torch.randn(1, 3, 224, 224))
slim_model = pruner.run(model)
print(pruner.summary())   # params_before/after, flops_before/after
```

Pruning drops accuracy immediately, so fine-tune for a few epochs afterward to recover it.

### Gradual pruning during training

Pruning 50% in one shot hurts more than pruning gradually. `PruningSchedule` ramps sparsity up over several epochs while training, so accuracy heals between steps.

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

`sparsity(model)` reports the fraction of weights that are exactly zero.

## Notes

- Unstructured pruning is mostly a research tool here. It reduces the non-zero weight count but will not speed up inference on ordinary hardware. Use structured pruning for real edge speedups.
- Always fine-tune after pruning, then re-check accuracy with the [runner's gates](../README.md).

See the [optimization overview](../README.md) for combining pruning with quantization in one recipe.
