# Step 15 — was the incumbent handicapped?

At 70% retention. The last pairing gives the length rule a reconstruction no one can deploy: the best estimator per case, chosen with hindsight.

      panel             screen                                     reconstruction  rate_above_0.5_at_70  mean_abs_error_at_70  retain_all_rate
development outage-length rule information-conditioned policy (used in the paper)                0.0923                0.1536           0.1487
development outage-length rule               always donor ridge, else climatology                0.0957                0.1597           0.1498
development outage-length rule                          always smooth climatology                0.1979                0.2880           0.2689
development outage-length rule               oracle over methods (NOT deployable)                0.0472                0.0903           0.0946
development        certificate   deployable estimators, chosen by the certificate                0.0293                0.0658           0.1456
   reserved outage-length rule information-conditioned policy (used in the paper)                0.0936                0.1478           0.1461
   reserved outage-length rule               always donor ridge, else climatology                0.0956                0.1506           0.1467
   reserved outage-length rule                          always smooth climatology                0.1539                0.2253           0.2203
   reserved outage-length rule               oracle over methods (NOT deployable)                0.0419                0.0772           0.0846
   reserved        certificate   deployable estimators, chosen by the certificate                0.0253                0.0563           0.1384

## Certificate minus the length rule armed with the oracle reconstruction

```json
{
  "development": {
    "point": -0.01782894044151195,
    "low": -0.022097895397123025,
    "high": -0.010733673589320484,
    "se": 0.0028723816943927167,
    "n_clusters": 110
  },
  "reserved": {
    "point": -0.01650382888830209,
    "low": -0.021291830357236724,
    "high": -0.007230585480486948,
    "se": 0.0035485836937395637,
    "n_clusters": 36
  }
}
```
