# Step 19 — is the headline carried by the largest agencies?

Contrast in percentage points; negative favours the certificate.

      panel           weighting  point    low   high  n_units
development case-equal (pooled) -6.335 -7.098 -5.483      NaN
development       network-equal -5.002 -5.747 -4.282    110.0
development       station-equal -4.237 -4.747 -3.770    351.0
development      provider-equal -5.409 -7.275 -3.768      9.0
   reserved case-equal (pooled) -7.011 -8.656 -5.332      NaN
   reserved       network-equal -5.822 -7.246 -4.416     36.0
   reserved       station-equal -5.535 -6.686 -4.428    103.0
   reserved      provider-equal -6.295 -8.269 -4.098      6.0

## Distribution over individual networks

```json
{
  "development": {
    "n_networks": 110,
    "median": -4.649020748497188,
    "share_favouring_certificate": 0.9,
    "q90": -0.1775147928994066,
    "worst": 4.49438202247191
  },
  "reserved": {
    "n_networks": 36,
    "median": -4.99643513827911,
    "share_favouring_certificate": 0.8333333333333334,
    "q90": 0.0,
    "worst": 2.8169014084507045
  }
}
```
