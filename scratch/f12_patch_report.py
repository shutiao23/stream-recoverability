"""Scratch patcher: splice the retention and reproduction text into script 247."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()

# --- retention mechanics ---------------------------------------------------
i = next(k for k, l in enumerate(lines) if '"- Matching removes no case that was comparable' in l)
j = next(k for k, l in enumerate(lines) if '"- Cases where K actually binds' in l)
assert "unusable in the original specification" in lines[i + 3], lines[i + 3]
assert "max_abs_count_gap_paired" in lines[j + 3], lines[j + 3]

new_retention = [
    '        "- Retention is above 100% for a mechanical reason, not because matching adds cases:",',
    '        f"  every one of the {int(retention[\'n_paired_original\']):,} original pairs is retained"',
    '        f" ({int(retention[\'n_paired_original_only\'])} dropped), and {int(retention[\'n_paired_matched_only\'])} cases become",',
    '        "  fittable that the original specification could not fit at all. A wide, gappy donor subset",',
    '        "  can leave too few complete training rows for the ridge; truncating to K recovers those",',
    '        f"  cases ({100 * float(retention[\'share_matched_only_where_truncated\']):.0f}% of the recovered cases had",',
    '        f"  more visible strong donors than K: on average {_fmt(retention[\'mean_visible_strong_matched_only\'], 2)} visible",',
    '        f"  strong donors truncated to K = {_fmt(retention[\'mean_k_matched_only\'], 2)}). Matching therefore loses no",',
    '        "  comparable case and recovers a few.",',
    '        "- Cases where K actually binds (the strong arm had more visible donors than K):",',
    '        f"  {100 * float(retention[\'share_strong_truncated\']):.1f}%; weak arm: {100 * float(retention[\'share_weak_truncated\']):.1f}%.",',
    '        "- Donor-count gap in the unmatched paired sample: mean |n_strong - n_weak| =",',
    '        f"  {_fmt(retention[\'mean_abs_count_gap_paired\'], 3)}, max = {retention[\'max_abs_count_gap_paired\']}.",',
]
lines[i : j + 3] = new_retention

# --- reproduction qualification -------------------------------------------
k = next(idx for idx, l in enumerate(lines) if "\"against {reproduction['frozen_n_paired']:,} frozen.\"," in l)
assert 'f"Case-level check:' in lines[k + 2], lines[k + 2]
qualification = [
    '        "That is a statistical reproduction, not a bit-for-bit one, and the gap is itself part of the",',
    '        "provenance finding: the frozen table cannot be regenerated exactly from the committed code.",',
    '        f"Only {reproduction[\'case_level\'].get(\'joined_cases\', 0):,} of the {reproduction[\'frozen_n_cases\']:,} frozen cases share a",',
    '        "(network, station, year, realization) key with this recomputation, because the outage",',
    '        "realizations are drawn from a stream whose position depends on the code revision; among the",',
    '        f"cases that do join, {100 * float(reproduction[\'case_level\'].get(\'longest_run_agreement\', float(\'nan\'))):.1f}% have the same",',
    '        f"outage geometry and {100 * float(reproduction[\'case_level\'].get(\'donor_count_agreement\', float(\'nan\'))):.1f}% the same donor counts.",',
    '        f"The published number is recovered to {_fmt(reproduction[\'point_abs_diff_c\'], 4)} C, far inside the bootstrap",',
    '        f"standard error of {_fmt(unmatched[\'se_c\'], 4)} C, so the sentence is not wrong about the effect; the",',
    '        "artifact is unreproducible as an artifact.",',
    '        "",',
]
lines[k + 1 : k + 3] = qualification

p.write_text("\n".join(lines) + "\n")
print("patched")
