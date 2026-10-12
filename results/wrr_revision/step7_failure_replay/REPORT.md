# Step 7 — realistic failure replay

Same complete-year hottest-30 endpoint as Step 5. Gap interiors are hidden
before prediction so adjacent outages cannot supply boundaries. Heat-event
overlap uses a training-period per-DOY 90th percentile and a 3-day run;
those labels are post-hoc diagnostics, not deployment inputs.

Geometry: month, length, and count from years before the evaluation year
(including incomplete years and other stations in the network when the
target itself has no natural gaps), transplanted onto later complete years.
Co-missing: donors are masked on the same windows.

## Natural transplanted geometry (918 eval station-years, 42 networks)

| Policy | \(B_q\) | vs simple | harm | adopt | abs. error |
|---|---:|---:|---:|---:|---:|
| Always simple | +0.244 | 0 | 0.16 | 1.00 | 0.20 |
| Always donor-only | +0.227 | −0.017 | 0.12 | 0.80 | 0.22 |
| Length/season | +0.051 | −0.194 | 0.04 | 0.12 | 0.45 |
| All default | 0 | −0.244 | 0 | 0 | 0.50 |

Default absolute error is lower than on archived experimental grids (0.50 vs
0.77 °C) because transplanted gaps are shorter/rarer. The simple policy
remains beneficial.

## Co-missing donors (876 eval station-years)

Donor-only is unsupported (adopt 0, \(B_q\) 0), as required of a negative
control. Always-simple (air / interpolation / climatology) is +0.024 °C
with harm 0.30. Oracle headroom is +0.061. Hiding donors removes most of
the benefit; it does not justify keeping an imputed full donor model
(Step 4 quality cells).
