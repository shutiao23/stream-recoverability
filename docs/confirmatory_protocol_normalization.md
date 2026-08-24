# Confirmatory manifest protocol normalization

The acquired `external_upper_middle_chattahoochee_v1` observations were bound
to the byte identity of `configs/design_freeze_v4.yaml` at acquisition. A later
protocol commit added only the internal development event-catalog declarations
at `data_versions.event_catalogs`; it did not alter any external site, period,
variable, provider, quality, split, mask, model, or evaluation rule.

Before evaluate-once execution, the external provenance manifest was therefore
normalized to:

- current design SHA-256
  `b1cb3823503b6b47a1f90b7314e3d0b25420c67c44f176e49841e21d90919bc1`;
- current finalized-roster SHA-256
  `4ff6a0a1bed1bed780bf212a5fb343008c394a31003bade9ae9535fa7bfd067c`.

The current roster has the same nine selected traditional models, the same
`donor_regression` best-traditional designation, and the same
`framework_only` proposed-model decision as the roster that originally opened
the public external inputs. No observation byte, split, request, feasibility
mask, prediction, or performance metric was changed or inspected by this
normalization. The manifest sidecar was regenerated after these identity-only
changes.
