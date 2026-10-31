# Confirmatory manifest protocol normalization

The acquired `external_upper_middle_chattahoochee_v1` observations were recorded
against `configs/design_freeze_v4.yaml` at acquisition. A later
protocol commit added only the internal development event-catalog declarations
at `data_versions.event_catalogs`; it did not alter any external site, period,
variable, provider, quality, split, mask, model, or evaluation rule.

Before evaluate-once execution, the external provenance manifest was therefore
normalized to refer to the current design and the current finalized roster.

The current roster has the same nine selected traditional models, the same
`donor_regression` best-traditional designation, and the same
`framework_only` proposed-model decision as the roster that originally opened
the public external inputs. No observation byte, split, request, feasibility
mask, prediction, or performance metric was changed or inspected by this
normalization. The manifest sidecar was regenerated after these identity-only
changes.
