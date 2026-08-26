# FOEN protocol deviation: failed opaque pilot v1 and query lock v2

Recorded 2026-08-26 after the first byte-custody pilot and before any retry.

## What happened without opening sealed bodies

Commit `3918d5dcfc758429acf9041bdad177a5f9ae6209` executed the locked v1
template for the prospective sealed Doubs network. The custody registry records
208/208 HTTP-200 bodies (four stations × 52 calendar years), but every body has
the same 986-byte length and the same SHA-256:

`cfcfc7a891b65acbd324af50aba2f62a3685d5f60f177d4c09b719595283c0c4`.

That fact comes only from the strict registry and filesystem metadata. No
existing mode-000 body was opened, decoded, or unsealed. The 208 objects remain
in the v1 provider vault as failed-pilot custody. They are never evidence, never
eligible for QC, never resumed by v2, and must never be unsealed merely to read
the provider error.

## Diagnosis using schema and metadata-only probes

FOEN schema introspection establishes:

- station `no`: `String`; `_eq` accepts `String`;
- observation `timestamp`: `AWSDateTime`; `_gte`/`_lt` accept `AWSDateTime`;
- observation `releaseState`: output `String`;
- `Water_Observations_Data1DayMean_Filter` permits `timestamp`,
  `parameterName`, `value`, `station`, `_and`, `_or`, and `_not`—it does **not**
  permit `releaseState`.

Therefore the suspected `$from: AWSDateTime!` type is not the defect. The v1
template's provider-side `releaseState: {_in: ["2", "3"]}` filter is invalid.
A station-2016 compile probe using the v1 filter shape, while deliberately
omitting the `value` selection, returned GraphQL `WrongType`: the `where` object
contains a field not in `Water_Observations_Data1DayMean_Filter`.

A second station-2016 probe removed only that filter and selected timestamp,
parameter, unit, release state, and station number—again no `value`. It compiled
without errors and returned seven metadata rows for 1–7 January 2025. This
verifies the exact variables and filter shape used by v2 without querying a
temperature value. Introspection separately confirms that `value` is an output
`Float`; the value-bearing v2 template itself has not been executed.

Machine-readable evidence:
`results/framework/public_catalog/foen_graphql_schema_audit_v2.json`.

## Prospective v2 correction

The station membership, roles, seed, canonical split SHA, and catalog SHA do not
change. Only the future request contract changes:

- v1 template SHA (retired):
  `978247efe815a79863e0383a3ae1e8c293642ec245d7205bd13a46b2ec3a446d`;
- v2 template: `configs/foen_daily_value_query_v2.graphql`;
- v2 template SHA:
  `11ace60436fe6edb9836c0d599cd3e5fa722c567270feeb7aa10c9d08de063ff`;
- v2 removes the invalid `releaseState` input filter;
- `releaseState` remains in the opaque response. State 2/3 filtering occurs only
  after the separately authorized one-time unseal—not in development custody.

The corrected lock is `configs/foen_prospective_split_v2.yaml`. It uses a new v2
vault, registry, and registry schema. This prevents the safe-resume path from
mistaking any of the 208 v1 objects for a v2 response.

## Retry gate

No full download may follow merely because the v2 request returns HTTP 200. The
one-network v2 pilot must first register 208 new v2 objects and show more than
one distinct response SHA across the varied station/year requests. This is an
opaque-byte diversity guard, not value inspection or scientific QC. If all v2
pilot bodies are again byte-identical, the full run fails closed and no body is
opened to diagnose it.

This correction is an API-schema defect repair. It does not change prospective
networks, statistical gates, QC thresholds, or the claim that Swiss currently
has zero qualified/T8 networks.
