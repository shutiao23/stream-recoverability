"""Scratch patcher: insert the distribution section into the F12 report."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()

# 1. write_report signature: add distributions
i = next(k for k, l in enumerate(lines) if l.strip() == "verdict: dict[str, object],")
lines.insert(i, "    distributions: dict[str, object],")

# 2. main(): pass distributions
i = next(k for k, l in enumerate(lines) if l.strip() == "verdict=verdict,")
lines.insert(i, "        distributions=distributions,")

# 3. report body: insert the section before the verdict section
anchor = next(k for k, l in enumerate(lines) if '"## Does the qualitative claim survive?",' in l)
section = [
    '        "## What the +0.08 C mean is made of",',
    '        "",',
    '        "The contrast is a mean over a pre-registered design that deliberately mixes outage",',
    '        "geometries, including outages that never touch the hottest 30 days, where completing the",',
    '        "gap cannot change the annual metric at all. The mean is therefore not a typical-case cost,",',
    '        "and the report says so rather than letting the single number carry the reading.",',
    '        "",',
    '        "| sample | n | mean (C) | median (C) | share > 0 | share = 0 | share < 0 | p90 (C) | top decile share of positive mass |",',
    '        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",',
    '    ]',
    '    for label, key in (',
    '        ("matched, exact K (top_of_half)", "matched_exact_k_top_of_half"),',
    '        ("unmatched, two-arm sample", "unmatched_original"),',
    '        ("unmatched, frozen published sample", "frozen_original"),',
    '    ):',
    '        block = distributions.get(key, {})',
    '        if not block.get("n"):',
    '            continue',
    '        lines.append(',
    '            f"| {label} | {block[\'n\']:,} | {_fmt(block[\'mean_c\'])} | {_fmt(block[\'median_c\'])} | "',
    '            f"{100 * float(block[\'share_positive\']):.1f}% | {100 * float(block[\'share_exactly_zero\']):.1f}% | "',
    '            f"{100 * float(block[\'share_negative\']):.1f}% | {_fmt(block[\'p90_c\'])} | "',
    '            f"{100 * float(block[\'top_decile_share_of_positive_mass\']):.0f}% |"',
    '        )',
    '    lines += [',
    '        "",',
    '        "The mean is carried by a minority of pairs: the sign is positive in roughly two fifths of",',
    '        "matched pairs, about a third are exact ties, and the largest decile of differences supplies",',
    '        "most of the positive mass. That structure is a property of the endpoint, not of the matching:",',
    '        "the frozen sample shows the same shape. The stratified estimate below shows where it comes",',
    '        "from.",',
    '        "",',
    '        "| stratum | n paired | point (C) | 95% CI |",',
    '        "| --- | --- | --- | --- |",',
    '    ]',
    '    for row in contrasts.loc[contrasts["spec"] == "matched_exact_k_stratum"].itertuples():',
    '        lines.append(',
    '            f"| arm={row.arm}, overlap={row.arm} | {row.n_paired:,} | {_fmt(row.point_c)} | "',
    '            f"{_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"',
    '        )',
    '    lines += [',
    '        "",',
    '        "Every stratum is positive and every stratum interval excludes zero, so the pooled mean is",',
    '        "not an artefact of pooling; its size is an average over strata that differ by more than an",',
    '        "order of magnitude.",',
    '        "",',
]
lines[anchor:anchor] = section
p.write_text("\n".join(lines) + "\n")
print("patched distribution section")
