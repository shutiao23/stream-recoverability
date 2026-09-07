"""WRR revision experiments: problem definition, fair recovery, decisions, mechanism."""

from stream_recoverability.experiments.wrr_revision.benefit import (
    attach_component_predictors,
    difference_identity_gap,
    history_switch_rule,
    ridge_benefit_predictor,
)
from stream_recoverability.experiments.wrr_revision.decision import (
    choose_tau,
    evaluate_rules,
    policy_metrics,
    reliability_table,
)
from stream_recoverability.experiments.wrr_revision.paths import (
    GAP_GRID,
    PRIMARY_METRIC,
    SAME_INFORMATION_RECOVERERS,
)
from stream_recoverability.experiments.wrr_revision.score import (
    crossing_day,
    recoverer_duration_summary,
    score_network,
)
from stream_recoverability.experiments.wrr_revision.thermal import (
    benefit,
    exceedance_days,
    hottest_consecutive_mean,
    series_losses,
)

__all__ = [
    "GAP_GRID",
    "PRIMARY_METRIC",
    "SAME_INFORMATION_RECOVERERS",
    "attach_component_predictors",
    "benefit",
    "choose_tau",
    "crossing_day",
    "difference_identity_gap",
    "evaluate_rules",
    "exceedance_days",
    "history_switch_rule",
    "hottest_consecutive_mean",
    "policy_metrics",
    "recoverer_duration_summary",
    "reliability_table",
    "ridge_benefit_predictor",
    "score_network",
    "series_losses",
]
