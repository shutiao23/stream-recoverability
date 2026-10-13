"""Scratch patcher: attribute the unequal-count numbers to the right generation."""

from pathlib import Path

module = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
s = module.read_text()

old = """    frozen_controls = json.loads((PREFIX_DIR / "summary.json").read_text(encoding="utf-8"))["controls"]"""
new = """    frozen_gap = (
        frozen_cases["n_strong"].astype(int) - frozen_cases["n_weak"].astype(int)
    ).abs()
    frozen_controls = json.loads((PREFIX_DIR / "summary.json").read_text(encoding="utf-8"))["controls"]"""
assert old in s
s = s.replace(old, new, 1)

old = """        "frozen_controls_block": frozen_controls,"""
new = """        "frozen_unequal_count_cases": int((frozen_gap != 0).sum()),
        "frozen_unequal_count_share": float((frozen_gap != 0).mean()),
        "frozen_max_abs_count_gap": int(frozen_gap.max()),
        "frozen_controls_block": frozen_controls,"""
assert old in s
s = s.replace(old, new, 1)
module.write_text(s)

script = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = script.read_text().splitlines()
start = next(k for k, l in enumerate(lines) if "- Frozen `donor_controls.parquet` records `n_strong` and `n_weak` per case; they differ in" in l)
end = next(k for k, l in enumerate(lines) if "donors. The count was not fixed." in l)
assert end - start == 3, (start, end, lines[start:end + 1])
block = [
    '        "- Frozen `donor_controls.parquet` records `n_strong` and `n_weak` per case; they differ in",',
    '        f"  {reproduction[\'frozen_unequal_count_cases\']:,} of {reproduction[\'frozen_n_cases\']:,} frozen cases",',
    '        f"  ({100 * float(reproduction[\'frozen_unequal_count_share\']):.1f}%), by up to {reproduction[\'frozen_max_abs_count_gap\']} donors.",',
    '        "  The recomputation shows the same pattern:",',
    '        f"  {retention[\'n_cases_with_unequal_counts\']:,} of {retention[\'n_cases_total\']:,} cases",',
    '        f"  ({100 * float(retention[\'share_cases_with_unequal_counts\']):.1f}%). The count was not fixed.",',
]
lines[start : end + 1] = block
script.write_text("\n".join(lines) + "\n")
print("patched attribution")
