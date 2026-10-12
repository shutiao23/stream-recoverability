# Claim matrix: empirical-transfer route

| Claim | Evidence required | Current evidence | Status and allowed language |
| --- | --- | --- | --- |
| C1: fitting-period empirical curves rank later loss across networks | Inner-fitting-year artificial gaps; outer evaluation; network-level rank primary; complete-panel fallback audit; new outcome panel | First panel: supported-horizon empirical versus simple network Spearman 0.922 versus 0.687; complete-panel 0.767 versus 0.563, while pooled rank and \(R^2\) favor simple. Second panel: supported-horizon empirical network Spearman 0.805 on 874 units; complete-panel empirical 0.715 versus simple 0.614 after 572 fallbacks | Reproduced with independent recovery outcomes under an internally hash-bound amendment; “outperformed at directly supported horizons and in network-level rank,” not an unqualified all-scale advantage or externally preregistered confirmation |
| C2: analytic conditional risk saturates and does not replace empirical stress testing | Fixed-station horizon decomposition and same-fold incremental-value tests | Analytic risk 0.379→0.451 °C while realized loss 0.544→4.719 °C; linear increment after simple \(\Delta R^2=0.0171\); learned-model increment 0.0033 | Supported mechanism and negative method result; describe conditional covariance as a Gaussian lower bound, not realized error |
| C3: transfer depends on model class and domain, and ranking does not imply a decision guarantee | Full statistical roster, bounded BiLSTM, independent air2stream-equivalent subset, domain reliability, interval endpoints, and exact triage | Three statistical families retain rank direction; BiLSTM and air2stream-equivalent station-gap transfer is weak; first-panel US slope 0.954 versus non-US 0.753; second-panel empirical slope 0.938 on supported units and 0.950 overall; second empirical interval width/loss 8.40; both exact triage rules release zero | Rank and near-unit calibration reproduced for the primary family, but broad model-class transfer, efficient intervals, and safe-fill control are not established |
| C4: placement improves realized network outcomes | Independent leave-k-station-out replay against MI, QR, even, random, and oracle comparators with a prespecified utility criterion | A 14-network development replay favors minimax; on 13 complete second-panel networks, minimax regret was 0.241 °C versus random 0.256 °C | Directionally lower regret, but no prespecified margin or significance threshold; no confirmatory utility claim or sensor-removal recommendation |
| P1f: empirical ranking transfers to recurrent reconstruction | Actual LSTM, outcome-blind multi-provider subset, fitting-year-only training | BiLSTM on 14 networks/165 cells: empirical-versus-LSTM Spearman 0.338 station-gap and 0.631 network; 92.9% hit the five-epoch cap | Broad transfer not established; bounded post-confirmation sensitivity, not converged SOTA or a full roster |
| P1h: empirical ranking transfers to a process model | Published process equation with aligned air temperature and discharge on independent networks | air2stream-8-equivalent on eight second-panel US networks/89 cells: empirical-versus-process Spearman 0.173 station-gap and 0.238 network | Independent process baseline implemented, but transfer is weak; alternate optimizer, US-only scope, and day-boundary mismatch remain |
| P1i: artificial-gap empirical ranking transfers to field-outage geometry | Matched station/network geometry comparison with paired network bootstrap | 49 networks/1,327 planted items: natural empirical network Spearman 0.566 versus artificial 0.734; paired delta -0.168 (-0.328, -0.012); 85.8% network-mean fallback | Moderate ordering remains but rank and calibration degrade; actual missing days have no truth and failure selection is unresolved |
| P3: climate or regulation explains calibration heterogeneity | Network random-intercept-and-slope models with phase interactions and external strata | Simple maritime slope 0.649 versus arid/semiarid 1.160, interaction \(p = 0.0024\); empirical climate interactions nonsignificant; regulated/unregulated empirical slopes 0.887/0.741, interaction \(p = 0.119\) | Descriptive effect modification only; HUC2 bands are broad, GAGES-II status is not causal, and empirical diagnostics include boundary warnings |

## Primary reporting order

1. Second-confirmation direct-horizon and complete-panel network rank.
2. First-panel supported-only and complete-panel comparison with the simple model.
3. Analytic saturation mechanism and incremental-value result.
4. BiLSTM, air2stream-equivalent, and matched-geometry boundaries.
5. Interval, domain, heterogeneity, placement, and triage boundaries.

## Claims not supported

- Conditional covariance is a novel sensor-design objective.
- Pooled station-gap rank substitutes for network-level inference.
- Calibration or a safe-fill threshold transfers without local validation.
- Three-network placement replay supports station removal.
- Post-confirmation adaptation is an independent confirmation.
- Reservoir operation caused a calibration failure.
