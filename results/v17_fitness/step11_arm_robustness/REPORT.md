# Step 11 — robustness of the headline result to the outage design

The pooled case set mixes a stratified arm, built to span the decision space, with an empirical arm drawn from the outage geometry these networks actually experience. Their base rates differ by an order of magnitude, so the two must be reported separately.

      panel        arm  n_cases  base_rate_retain_all  length_rule_at_70  certificate_at_70  peak_overlap_at_70  random_at_70  absolute_points_saved  relative_reduction  contrast_points  ci_low_points  ci_high_points  johnson91_retention  johnson91_rate  certificate_at_johnson_retention  self_selected_retention  self_selected_rate_retained
development  empirical    14995                0.0735             0.0252             0.0038              0.0105        0.0755                 2.1341              0.8485          -2.1341        -3.4543         -1.2581               0.8385          0.0368                            0.0122                   0.8516                       0.0137
development stratified    25709                0.1925             0.1458             0.0617              0.1140        0.1952                 8.4074              0.5768          -8.3908        -9.2484         -7.4685               0.6294          0.1373                            0.0455                   0.5735                       0.0368
development     pooled    40704                0.1487             0.0924             0.0293              0.0564        0.1497                 6.3068              0.6825          -6.3454        -7.1203         -5.5247               0.7064          0.0933                            0.0303                   0.6759                       0.0261
   reserved  empirical     4041                0.0423             0.0074             0.0011              0.0039        0.0410                 0.6363              0.8571          -0.7070        -2.3560          0.0545               0.9235          0.0316                            0.0091                   0.9045                       0.0049
   reserved stratified     6779                0.2080             0.1659             0.0778              0.1151        0.2067                 8.8093              0.5311          -8.6828       -10.4596         -6.5123               0.6308          0.1600                            0.0634                   0.5384                       0.0356
   reserved     pooled    10820                0.1461             0.0966             0.0253              0.0420        0.1439                 7.1297              0.7377          -7.1297        -8.9801         -5.4073               0.7401          0.1001                            0.0376                   0.6751                       0.0203

```json
{
  "pre_registered_test": "pooled cases, as declared in step9_freeze",
  "finding": "The relative reduction in consequential-error rate is stable across outage regimes; the absolute reduction is not, because the base rate differs by an order of magnitude between the empirical and stratified arms.",
  "declared_effect_points": 5.0,
  "meets_declared_effect": {
    "development_empirical": false,
    "development_stratified": true,
    "development_pooled": true,
    "reserved_empirical": false,
    "reserved_stratified": true,
    "reserved_pooled": true
  },
  "interval_excludes_zero": {
    "development_empirical": true,
    "development_stratified": true,
    "development_pooled": true,
    "reserved_empirical": false,
    "reserved_stratified": true,
    "reserved_pooled": true
  },
  "lesson": "The freeze should have weighted the arms explicitly. Reporting the pooled number alone would overstate what an archive with ordinary outage geometry stands to gain."
}
```
