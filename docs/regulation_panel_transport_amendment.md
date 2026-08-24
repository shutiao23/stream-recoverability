# Regulation-panel transport amendment v1

The frozen modern USGS `/daily` download completed 26 of 56 restartable batches and
then returned HTTP 429 with `OVER_RATE_LIMIT`; no Water Data API key is available in
the execution environment. No station metric, class contrast, AUC, regression, or
distance profile had been calculated when this amendment was sealed.

USGS documents `/dv` as the legacy predecessor of `/daily` and maps parameter,
statistic, date, value, and approval fields between them. The fallback therefore
changes transport, not the provider, parameter (`00010`), statistic (`00003`), dates,
or approval rule. It is restricted to the 1,335 exact GAGES-II overlap stations with
exactly one primary series in the already cached modern metadata. The 26 stations
with multiple primary series are excluded as transport-ambiguous and cannot be
spliced. An exact station-date-value equivalence audit over every available modern
cache overlap is required before any fallback result is accepted.

The resulting analysis is named the **transport-limited maximum legal panel**. It may
report its frozen estimates but may not be described as completing the full original
roster. A later API-keyed reproduction can fill the 26 ambiguous sites without
changing this result or reopening either freeze.

