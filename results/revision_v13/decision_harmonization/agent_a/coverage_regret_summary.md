# Fixed-coverage coverage-regret summary (Part A)

Released sets: top c fraction of the 1,440 first-panel units ranked by a
confidence criterion (a) ambiguity margin (desc), (b) mean width (asc),
(c) support completeness = # families with unit-level fitting-period stress
(desc, then margin desc). k = round(c*1440). Regret definition identical to
t09: per-unit regret = L(selected) - min_f L(f); network-balanced regret =
mean over networks with >=1 released unit of within-network mean regret.
The current 8.5% point = the t09 support-any + ambiguity (delta=0.10,
lambda=0.5) abstention set: 123 units, 8 networks, regret 0.0067.

| method | c | criterion | released_units | released_networks | unit_cov | net_cov | net_balanced_regret | pooled_regret | sel_acc | top2_hit |
|---|---|---|---|---|---|---|---|---|---|---|
| proposed | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.1147 | 0.1373 | 0.5167 | 0.9917 |
| proposed | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.0978 | 0.1124 | 0.5238 | 0.9812 |
| proposed | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0719 | 0.0772 | 0.4903 | 0.9778 |
| proposed | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0662 | 0.0737 | 0.4901 | 0.9762 |
| proposed | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0977 | 0.0875 | 0.5625 | 0.9903 |
| proposed | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0837 | 0.0785 | 0.5288 | 0.9802 |
| best_fixed | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.1300 | 0.1491 | 0.5764 | 0.9583 |
| best_fixed | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.1085 | 0.1281 | 0.5506 | 0.9524 |
| best_fixed | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0462 | 0.0761 | 0.5431 | 0.9861 |
| best_fixed | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0561 | 0.0709 | 0.5635 | 0.9712 |
| best_fixed | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0813 | 0.1045 | 0.5806 | 0.9653 |
| best_fixed | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0730 | 0.0862 | 0.5754 | 0.9554 |
| global_cv | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.1300 | 0.1491 | 0.5764 | 0.9583 |
| global_cv | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.1085 | 0.1281 | 0.5506 | 0.9524 |
| global_cv | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0462 | 0.0761 | 0.5431 | 0.9861 |
| global_cv | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0561 | 0.0709 | 0.5635 | 0.9712 |
| global_cv | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0813 | 0.1045 | 0.5806 | 0.9653 |
| global_cv | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0730 | 0.0862 | 0.5754 | 0.9554 |
| per_net_cv | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.0613 | 0.0536 | 0.7056 | 0.9833 |
| per_net_cv | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.0487 | 0.0442 | 0.6865 | 0.9742 |
| per_net_cv | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0218 | 0.0209 | 0.7083 | 0.9889 |
| per_net_cv | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0278 | 0.0239 | 0.6915 | 0.9812 |
| per_net_cv | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0479 | 0.0441 | 0.7000 | 0.9861 |
| per_net_cv | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0405 | 0.0372 | 0.6806 | 0.9762 |
| gap_rule | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.1347 | 0.1475 | 0.4819 | 0.9861 |
| gap_rule | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.1114 | 0.1219 | 0.4960 | 0.9851 |
| gap_rule | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0739 | 0.0785 | 0.4597 | 0.9806 |
| gap_rule | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0761 | 0.0822 | 0.4454 | 0.9812 |
| gap_rule | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0936 | 0.0995 | 0.5083 | 0.9875 |
| gap_rule | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0852 | 0.0877 | 0.4940 | 0.9871 |
| random | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.3868 | 0.3928 | 0.3347 | 0.6698 |
| random | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.3227 | 0.3337 | 0.3337 | 0.6672 |
| random | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.2023 | 0.2226 | 0.3263 | 0.6622 |
| random | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.1930 | 0.2107 | 0.3256 | 0.6623 |
| random | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.3239 | 0.3288 | 0.3335 | 0.6692 |
| random | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.2676 | 0.2790 | 0.3323 | 0.6672 |
| oracle | 0.5 | a_ambiguity_margin | 720 | 42 | 0.5000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| oracle | 0.7 | a_ambiguity_margin | 1008 | 42 | 0.7000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| oracle | 0.5 | b_mean_width | 720 | 25 | 0.5000 | 0.5952 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| oracle | 0.7 | b_mean_width | 1008 | 35 | 0.7000 | 0.8333 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| oracle | 0.5 | c_support_completeness | 720 | 42 | 0.5000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
| oracle | 0.7 | c_support_completeness | 1008 | 42 | 0.7000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

Reference points:

| method | released_units | released_networks | net_balanced_regret | pooled_regret | sel_acc | top2_hit |
|---|---|---|---|---|---|---|
| proposed | 123 | 8 | 0.0067 | 0.0121 | 0.8455 | 1.0000 |
| best_fixed | 123 | 8 | 0.1508 | 0.2021 | 0.3415 | 0.9837 |
| global_cv | 123 | 8 | 0.1508 | 0.2021 | 0.3415 | 0.9837 |
| per_net_cv | 123 | 8 | 0.1636 | 0.0471 | 0.7967 | 1.0000 |
| gap_rule | 123 | 8 | 0.1447 | 0.1402 | 0.5610 | 0.9919 |
| random | 123 | 8 | 0.3509 | 0.3407 | 0.3293 | 0.6557 |
| oracle | 123 | 8 | 0.0000 | 0.0000 | 1.0000 | 1.0000 |

No-abstention (c=1.0, all 1,440 units):

| method | net_balanced_regret | pooled_regret | sel_acc | top2_hit |
|---|---|---|---|---|
| proposed | 0.0850 | 0.0932 | 0.5153 | 0.9722 |
| best_fixed | 0.0815 | 0.1039 | 0.5437 | 0.9556 |
| global_cv | 0.0815 | 0.1039 | 0.5437 | 0.9556 |
| per_net_cv | 0.0383 | 0.0369 | 0.6687 | 0.9715 |
| gap_rule | 0.0927 | 0.1024 | 0.4854 | 0.9799 |
| random | 0.2628 | 0.2786 | 0.3303 | 0.6643 |
| oracle | 0.0000 | 0.0000 | 1.0000 | 1.0000 |
