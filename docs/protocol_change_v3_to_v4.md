# Protocol change: `design_freeze_v3` to `design_freeze_v4`

No v3 development-test or confirmatory performance was available when this amendment was frozen. v4 does not change models, hyperparameters, the 400-epoch cap, masks, temporal splits, external sites, or evaluation years.

The amendment closes the execution-contract migration:

- every executable stage derives the primary and sensitivity versions from the design;
- validation and development anchor catalogs are relabelled for `published_v2` only after date-axis, truth, natural-observation, and eligibility equivalence checks;
- the best-simple selection family excludes exact gap length and split-specific condition IDs, so one validation-selected target-T baseline maps to every dense development gap;
- dual-frontier and donor-C artifacts are required formal analysis outputs;
- donor-C inference uses paired uncertainty and a predeclared minimum meaningful difference of 0.01;
- the release gate consumes explicit evidence manifests and validates completion rather than discovering any convenient file by glob.

The bridge report is `metadata/anchor_bridge_published_v1_to_v2.json`. It contains structural counts and equivalence outcomes; v4 does not add digest-pinning requirements.
