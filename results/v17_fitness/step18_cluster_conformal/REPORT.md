# Step 18 — cluster-aware conformal calibration

Pooled calibration is valid for a population of networks. The cluster settings target validity inside a stated share of networks instead, by calibrating on the per-network conformal quantiles. The level is the share of calibration networks the scale is set to cover, and it buys site-level honesty with interval width.

calibration  marginal_coverage  per_network_mean  per_network_q10  per_network_min  share_below_0.85  median_width_c  rate_at_70
     pooled             0.9085            0.9035           0.8397           0.7778            0.1389          0.5352      0.0253
cluster_0.5             0.9089            0.9037           0.8407           0.7778            0.1389          0.5361      0.0253
cluster_0.6             0.9165            0.9120           0.8509           0.7778            0.1111          0.5518      0.0253
cluster_0.7             0.9321            0.9290           0.8708           0.8416            0.0556          0.6048      0.0253
cluster_0.8             0.9484            0.9448           0.9000           0.8416            0.0278          0.6845      0.0253
cluster_0.9             0.9635            0.9584           0.9261           0.8515            0.0000          0.7955      0.0253

```json
{
  "question": "can the interval be made honest at a single new site, and what does it cost?",
  "pooled": {
    "n_networks": 36,
    "mean": 0.9035332414215907,
    "median": 0.9132716049382716,
    "q10": 0.8396892795491974,
    "min": 0.7777777777777778,
    "share_below_0.80": 0.027777777777777776,
    "share_below_0.85": 0.1388888888888889
  },
  "cheapest_setting_with_no_network_below_0.85": "cluster_0.9",
  "cheapest": {
    "n_networks": 36,
    "mean": 0.9584058155955932,
    "median": 0.9613517550410755,
    "q10": 0.9260773292454437,
    "min": 0.8514851485148515,
    "share_below_0.80": 0.0,
    "share_below_0.85": 0.0
  },
  "width_cost_ratio": 1.4863891150927944,
  "screening_unaffected": true,
  "note": "The ranking the screen uses is a monotone transform of the bound, so a change of calibration scale cannot move the retention-error frontier at all. Only the interval and the self-selected operating point change."
}
```
