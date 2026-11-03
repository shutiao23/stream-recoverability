# Gaussian AR(1) bridge sampling

`stream_recoverability.experiments.tr_revision.baselines` provides two
implementations of the variance-preserving Gaussian AR(1) gap bridge. They
share the same AR(1) coefficients, boundary conditioning, and output layout
(`draws x observations`) but differ in how random numbers are assigned.

## `ar1_bridge` (legacy)

The legacy sampler allocates one `np.random.default_rng(seed)` and draws every
path's innovation in day-major order (`rng.normal(..., draws)` per gap day).
The stream consumed by a path therefore depends on the total number of paths:
a 20-path result is **not** a prefix of a 500-path result with the same seed.

This function is kept byte-for-byte unchanged so that historical results,
including the frozen r4 trajectory numbers, can be replayed exactly.

## `ar1_bridge_pathwise`

The pathwise sampler creates one independent stream per path:

```python
children = np.random.SeedSequence(seed).spawn(draws)
```

Path `i` is generated only from `np.random.default_rng(children[i])`. NumPy
spawns children deterministically and independently of the requested count, so
the first `N` paths are identical for any `draws >= N`. A pilot ensemble can
therefore be extended without regenerating or renumbering earlier paths.

The AR(1) recurrence, start-state handling, right-boundary conditioning, and
returned array are otherwise the same as the legacy sampler. Random draws are
consumed in path-major rather than day-major order, so the two functions do
not produce identical numbers for the same seed; they are statistically
equivalent.

## Status of frozen results

The frozen r4 trajectory numbers were produced with the legacy `ar1_bridge`
and are unchanged. A full trajectory replay with `ar1_bridge_pathwise` is
pending; no saved result or caller has been switched to the new sampler.
