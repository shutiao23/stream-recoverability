# Deep-training stability diagnosis

The frozen validation objective already scores four artificial-gap scenarios:
point, short block, long block, and station outage. Checkpoint histories for all
Stage-3 seeds contain finite train and validation losses, so the failures are not
explained by a whole-window validation target or numerical divergence.

The scaler is fitted once from the training split and is independent of model
seed. The unstable results instead coincide with premature checkpoint selection:
BRITS selected epochs 5, 56, and 125 across seeds 22, 33, and 11; proposed
selected 33, 173, and 214 across seeds 22, 33, and 11. Proposed seed 22's
validation score improved normally through epoch 33, then its station-outage
loss worsened. This is seed-dependent early selection and cross-regime
generalisation failure, not a non-finite optimisation run.

The v5 amendment therefore uses one simple validity label: `training_unstable`
when any required seed has `best_epoch < 50`. Such a model is excluded from the
formal roster. No conclusion about the usefulness of deep models is permitted
from excluded runs.
