# E3 — the axis comparison on Johnson et al.'s estimands

Sine-wave linear regression, three parameters, development cases, each scored at 0.47 of its own interannual standard deviation.

| endpoint       | protocol           |   base_rate |   auc_peak_overlap |   auc_warm_observed_fraction |   auc_transition_overlap |   auc_longest_run |   auc_missing_fraction |   auc_influence_hidden | best_axis        |
|:---------------|:-------------------|------------:|-------------------:|-----------------------------:|-------------------------:|------------------:|-----------------------:|-----------------------:|:-----------------|
| sine_mean      | repaired           |     0.09886 |             0.672  |                       0.8182 |                   0.7889 |            0.8454 |                 0.8447 |                 0.8447 | longest_run      |
| sine_mean      | observed_days_only |     0.3178  |             0.6673 |                       0.8396 |                   0.8274 |            0.9047 |                 0.9019 |                 0.9019 | longest_run      |
| sine_amplitude | repaired           |     0.1217  |             0.7236 |                       0.82   |                   0.7091 |            0.8152 |                 0.8123 |                 0.8308 | influence_hidden |
| sine_amplitude | observed_days_only |     0.3401  |             0.743  |                       0.833  |                   0.7009 |            0.8475 |                 0.8424 |                 0.8712 | influence_hidden |
| sine_phase     | repaired           |     0.1187  |             0.5829 |                       0.7674 |                   0.8314 |            0.8357 |                 0.8346 |                 0.8474 | influence_hidden |
| sine_phase     | observed_days_only |     0.3358  |             0.5899 |                       0.8003 |                   0.891  |            0.8975 |                 0.8984 |                 0.9161 | influence_hidden |

## Network-clustered contrasts

| endpoint       | left                            | right            |     point |       low |      high | excludes_zero   |
|:---------------|:--------------------------------|:-----------------|----------:|----------:|----------:|:----------------|
| sine_mean      | missing_fraction                | peak_overlap     |  0.1727   |  0.1572   |  0.1921   | True            |
| sine_mean      | transition_overlap              | peak_overlap     |  0.117    |  0.1002   |  0.1382   | True            |
| sine_mean      | transition_overlap              | missing_fraction | -0.05579  | -0.06297  | -0.04904  | True            |
| sine_mean      | influence_hidden_sine_mean      | peak_overlap     |  0.1727   |  0.1572   |  0.1921   | True            |
| sine_mean      | influence_hidden_sine_mean      | missing_fraction |  0        |  0        |  0        | False           |
| sine_amplitude | missing_fraction                | peak_overlap     |  0.08864  |  0.07205  |  0.1067   | True            |
| sine_amplitude | transition_overlap              | peak_overlap     | -0.01448  | -0.03064  |  0.002923 | False           |
| sine_amplitude | transition_overlap              | missing_fraction | -0.1031   | -0.1111   | -0.09568  | True            |
| sine_amplitude | influence_hidden_sine_amplitude | peak_overlap     |  0.1072   |  0.09291  |  0.1243   | True            |
| sine_amplitude | influence_hidden_sine_amplitude | missing_fraction |  0.01855  |  0.0151   |  0.02226  | True            |
| sine_phase     | missing_fraction                | peak_overlap     |  0.2517   |  0.2365   |  0.2703   | True            |
| sine_phase     | transition_overlap              | peak_overlap     |  0.2485   |  0.2308   |  0.2699   | True            |
| sine_phase     | transition_overlap              | missing_fraction | -0.003215 | -0.01046  |  0.004009 | False           |
| sine_phase     | influence_hidden_sine_phase     | peak_overlap     |  0.2645   |  0.2488   |  0.2849   | True            |
| sine_phase     | influence_hidden_sine_phase     | missing_fraction |  0.01275  |  0.008995 |  0.01711  | True            |

## Verdicts against the declared predictions

```json
{
  "P1_mean_is_length_governed": {
    "prediction": "for the fitted mean, outage size beats peak-window overlap",
    "outcome": true,
    "auc_missing_fraction": 0.8447112411409406,
    "auc_peak_overlap": 0.6719641258230334
  },
  "P2_phase_is_transition_governed": {
    "prediction": "for the phase, the transition windows beat both peak-window overlap and outage length",
    "outcome": false,
    "auc_transition_overlap": 0.8313968422941572,
    "auc_peak_overlap": 0.5829087062657615,
    "auc_longest_run": 0.8356872314042069
  },
  "P3_amplitude_is_intermediate": {
    "prediction": "the amplitude's peak-overlap advantage lies between the other two",
    "peak_minus_length_by_endpoint": {
      "sine_mean": -0.1727471153179072,
      "sine_amplitude": -0.08864141122870839,
      "sine_phase": -0.25170330095077753
    }
  },
  "P4_influence_weighting_is_at_least_as_good": {
    "prediction": "the influence-weighted hidden mass is the best or joint-best axis",
    "best_axis_by_endpoint": {
      "sine_mean": "longest_run",
      "sine_amplitude": "influence_hidden",
      "sine_phase": "influence_hidden"
    },
    "influence_auc_by_endpoint": {
      "sine_mean": 0.8447112411409406,
      "sine_amplitude": 0.8308126553738895,
      "sine_phase": 0.8473616615593051
    }
  }
}
```
