"""Hyperparameter search with Optuna and OptunaCallback.

Demonstrates:
  1. Single-objective Optuna study (minimize val/loss) with OptunaCallback.
  2. Pruning with MedianPruner — multi-epoch intermediate reporting.
  3. Post-study analysis: best_params, best_value, trials_dataframe().
  4. Re-training a final model with the best found hyperparameters.
  5. Manual duck-typed trial — shows OptunaCallback works without Optuna.
"""

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models.architectures.factory import build_model
from mindtrace.models.training.trainer import Trainer
from mindtrace.models.training.optimizers import build_optimizer
from mindtrace.models.training.callbacks import OptunaCallback

# ── Optuna guard ───────────────────────────────────────────────────────────
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA = True
except ImportError:
    _OPTUNA = False
    print("SKIPPING optuna sections: pip install optuna")

# ── Synthetic data ─────────────────────────────────────────────────────────
NUM_CLASSES = 3
IN_CH       = 3
IMG_SIZE    = 32
N_TRAIN     = 256
N_VAL       = 64
BATCH       = 32

X_train = torch.randn(N_TRAIN, IN_CH, IMG_SIZE, IMG_SIZE)
Y_train = torch.randint(0, NUM_CLASSES, (N_TRAIN,))
X_val   = torch.randn(N_VAL,   IN_CH, IMG_SIZE, IMG_SIZE)
Y_val   = torch.randint(0, NUM_CLASSES, (N_VAL,))

train_loader = DataLoader(TensorDataset(X_train, Y_train), batch_size=BATCH, shuffle=True)
val_loader   = DataLoader(TensorDataset(X_val,   Y_val),   batch_size=BATCH)


# ── Section 1: Single-objective search (minimize val/loss) ─────────────────
print("\n── Section 1: Optuna single-objective (minimize val/loss) ──")

if _OPTUNA:
    def objective(trial: "optuna.Trial") -> float:
        lr        = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
        wd        = trial.suggest_float("weight_decay", 1e-5, 1e-1, log=True)
        hidden    = trial.suggest_categorical("hidden_dim", [256, 512])
        dropout   = trial.suggest_float("dropout", 0.0, 0.4, step=0.1)

        model = build_model(
            "resnet50", "mlp",
            num_classes=NUM_CLASSES,
            hidden_dim=hidden,
            pretrained=False,
            dropout=dropout,
        )
        optimizer = build_optimizer("adamw", model, lr=lr, weight_decay=wd)
        trainer   = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=optimizer,
            callbacks=[OptunaCallback(trial, monitor="val/loss")],
            device="auto",
        )
        trainer.fit(train_loader, val_loader, epochs=3)
        final_val_loss = trainer.history["val/loss"][-1]
        return final_val_loss

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=4, show_progress_bar=False)

    print(f"  Trials completed : {len(study.trials)}")
    print(f"  Best val/loss    : {study.best_value:.4f}")
    print(f"  Best params      : {study.best_params}")

    # Post-study pandas summary (optional)
    try:
        df = study.trials_dataframe()
        relevant_cols = [c for c in df.columns if "value" in c or "param" in c or "state" in c]
        print(f"  trials_dataframe columns: {relevant_cols}")
        print(f"  Best trial row:\n{df.loc[df['value'].idxmin(), relevant_cols].to_string()}")
    except Exception as e:
        print(f"  SKIPPING trials_dataframe: {e}")
else:
    print("  (optuna not installed — skipping)")

# ── Section 2: Pruning with MedianPruner ──────────────────────────────────
print("\n── Section 2: Optuna with MedianPruner ──")

if _OPTUNA:
    def pruning_objective(trial: "optuna.Trial") -> float:
        lr     = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
        hidden = trial.suggest_categorical("hidden_dim", [256, 512])

        model = build_model(
            "resnet50", "linear",
            num_classes=NUM_CLASSES,
            pretrained=False,
        )
        optimizer = build_optimizer("adam", model, lr=lr)
        cb = OptunaCallback(trial, monitor="val/loss")
        trainer = Trainer(
            model=model,
            loss_fn=nn.CrossEntropyLoss(),
            optimizer=optimizer,
            callbacks=[cb],
            device="auto",
        )
        # OptunaCallback reports val/loss each epoch and prunes weak trials.
        try:
            trainer.fit(train_loader, val_loader, epochs=5)
        except optuna.TrialPruned:
            pass  # Trainer sets stop_training=True before raise; history is intact.

        if not trainer.history.get("val/loss"):
            raise optuna.TrialPruned()
        return trainer.history["val/loss"][-1]

    pruner = optuna.pruners.MedianPruner(n_startup_trials=2, n_warmup_steps=1)
    pruning_study = optuna.create_study(direction="minimize", pruner=pruner)
    pruning_study.optimize(pruning_objective, n_trials=6, show_progress_bar=False)

    pruned   = [t for t in pruning_study.trials if t.state == optuna.trial.TrialState.PRUNED]
    complete = [t for t in pruning_study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"  Total trials   : {len(pruning_study.trials)}")
    print(f"  Completed      : {len(complete)}")
    print(f"  Pruned         : {len(pruned)}")
    if pruning_study.best_trial:
        print(f"  Best val/loss  : {pruning_study.best_value:.4f}")
        print(f"  Best params    : {pruning_study.best_params}")
else:
    print("  (optuna not installed — skipping)")

# ── Section 3: Train final model with best params ─────────────────────────
print("\n── Section 3: Final model with best hyperparameters ──")

if _OPTUNA:
    best = study.best_params
    print(f"  Using best params: {best}")

    final_model = build_model(
        "resnet50", "mlp",
        num_classes=NUM_CLASSES,
        hidden_dim=best.get("hidden_dim", 512),
        pretrained=False,
        dropout=best.get("dropout", 0.1),
    )
    final_opt = build_optimizer(
        "adamw", final_model,
        lr=best["lr"],
        weight_decay=best["weight_decay"],
    )
    final_trainer = Trainer(
        model=final_model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=final_opt,
        device="auto",
    )
    history = final_trainer.fit(train_loader, val_loader, epochs=5)
    print(f"  Final train/loss history : {[round(v, 4) for v in history['train/loss']]}")
    print(f"  Final val/loss history   : {[round(v, 4) for v in history['val/loss']]}")
    print(f"  Best val/loss achieved   : {min(history['val/loss']):.4f}")
else:
    # Fallback: just train a default model to show the pattern
    print("  Training fallback model (optuna not available)")
    fallback_model = build_model("resnet50", "mlp", num_classes=NUM_CLASSES, pretrained=False)
    fallback_opt   = build_optimizer("adamw", fallback_model, lr=3e-4, weight_decay=1e-2)
    fallback_trainer = Trainer(
        model=fallback_model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=fallback_opt,
        device="auto",
    )
    history = fallback_trainer.fit(train_loader, val_loader, epochs=3)
    print(f"  val/loss history: {[round(v, 4) for v in history['val/loss']]}")

# ── Section 4: Duck-typed trial (no optuna needed) ────────────────────────
print("\n── Section 4: Duck-typed trial — OptunaCallback without Optuna ──")

class DuckTrial:
    """Minimal trial object that satisfies OptunaCallback's interface."""
    def __init__(self):
        self.reports: list[tuple[float, int]] = []
        self._prune_after = 3           # simulate pruning after step 3

    def report(self, value: float, step: int) -> None:
        self.reports.append((value, step))
        print(f"    DuckTrial.report(value={value:.4f}, step={step})")

    def should_prune(self) -> bool:
        # Prune on step 3 to demonstrate the mechanism.
        if self.reports and self.reports[-1][1] >= self._prune_after:
            print(f"    DuckTrial.should_prune() → True (step={self.reports[-1][1]})")
            return True
        return False


duck_trial = DuckTrial()
duck_cb    = OptunaCallback(duck_trial, monitor="val/loss")

duck_model  = build_model("resnet50", "linear", num_classes=NUM_CLASSES, pretrained=False)
duck_opt    = build_optimizer("adam", duck_model, lr=1e-3)
duck_trainer = Trainer(
    model=duck_model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=duck_opt,
    callbacks=[duck_cb],
    device="auto",
)

# Trainer will call OptunaCallback.on_epoch_end each epoch;
# when should_prune() returns True, stop_training is set and training halts.
duck_trainer.fit(train_loader, val_loader, epochs=6)

print(f"  Epochs run before prune : {len(duck_trial.reports)}")
print(f"  Reports logged          : {[(round(v,4), s) for v, s in duck_trial.reports]}")
print(f"  stop_training flag      : {duck_trainer.stop_training}")

print("\nDone.")
