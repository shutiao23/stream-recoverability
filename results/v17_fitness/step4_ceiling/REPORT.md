# Step 4 — ceiling analysis and the go/no-go gate

No decision rule is fit until the prize inside its action space is known and compared with the resolution the reserved panel will have. Natural scale of the endpoint: 1.06 °C interannual SD.

Development cases: **40,704** on **110** networks, **4,045** station-years.

## Action spaces whose endpoint is mean benefit over the default

                              action_space  network_equal_mean_bq_c  headroom_over_deployed_c  headroom_in_natural_sd
   deployed information-conditioned policy                   0.1272                    0.0000                  0.0000
        oracle adopt/reject of that policy                   0.1648                    0.0376                  0.0355
oracle choice among reconstruction methods                   0.2069                    0.0798                  0.0753

## Action space whose endpoint is the consequential-error rate among retained years

 retention  oracle_rate_above_tolerance  oracle_mean_abs_error_c  retain_all_rate_above_tolerance  retain_all_mean_abs_error_c  headroom_rate_points  tolerance_c
       0.4                       0.0000                   0.0000                           0.1487                       0.2416               14.8683          0.5
       0.5                       0.0000                   0.0006                           0.1487                       0.2416               14.8683          0.5
       0.6                       0.0000                   0.0074                           0.1487                       0.2416               14.8683          0.5
       0.7                       0.0000                   0.0231                           0.1487                       0.2416               14.8683          0.5
       0.8                       0.0000                   0.0511                           0.1487                       0.2416               14.8683          0.5
       0.9                       0.0541                   0.1016                           0.1487                       0.2416                9.4580          0.5
       1.0                       0.1487                   0.2416                           0.1487                       0.2416                0.0000          0.5

## What the reserved panel can resolve

               endpoint  unit  between_network_sd  resolvable_margin_reserved  n_reserved_networks
       mean benefit B_q deg C              0.1390                      0.0454                   36
  absolute metric error deg C              0.1145                      0.0374                   36
indicator error > 0.5 C  rate              0.0825                      0.0269                   36

## Estimator error at the declared tolerances

      estimator  availability  mean_abs_error_c  rate_above_0.25  rate_above_0.5  rate_above_1.0  mean_error_in_natural_sd
  observed_days        0.9997            1.3052           0.3826          0.3187          0.2492                    1.2314
doy_climatology        1.0000            0.4015           0.3726          0.2665          0.1429                    0.3787
         policy        1.0000            0.2416           0.2453          0.1487          0.0677                    0.2279
  oracle_method        1.0000            0.1651           0.1703          0.0946          0.0398                    0.1558

## Gate

```json
{
  "resolvable_margin_bq_c": 0.04540527948252249,
  "resolvable_margin_rate": 0.026934087996805512,
  "gate_multiple": 3.0,
  "adopt_reject": {
    "ceiling_c": 0.03762903266329676,
    "required_c": 0.13621583844756746,
    "passes": false
  },
  "method_selection": {
    "ceiling_c": 0.07979524247768749,
    "required_c": 0.13621583844756746,
    "passes": false
  },
  "retain_exclude": {
    "ceiling_rate": 0.14868317610062892,
    "required_rate": 0.08080226399041654,
    "passes": true
  }
}
```
