"""Scratch patcher: final polish of the F12 report text."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()


def find(pred, start=0):
    return next(k for k, l in enumerate(lines) if k >= start and pred(l))


# (a)+(b) reproduction paragraph wording and tidy the case-level lead-in -----
i = find(lambda l: 'f"The unmatched number reproduces the frozen generation:' in l)
lines[i] = '        f"The unmatched number lands {_fmt(reproduction[\'point_abs_diff_c\'], 4)} C from the frozen generation: {_fmt(reproduction[\'recomputed_original_point_c\'])} C",'

j = find(lambda l: "realizations are drawn from a stream whose position depends on the code revision; among the" in l)
lines[j] = '        "realizations differ, which indicates that the frozen table was produced by a different revision",'
k = find(lambda l: 'f"cases that do join, {100 * float(reproduction[\'case_level\'].get(\'longest_run_agreement\'' in l)
lines.insert(
    k + 2,
    '        "of the pipeline than the one committed — a revision that, as the probe below shows, could",',
)
lines.insert(k + 3, '        "not run this branch at all.",')
# the standalone case-level paragraph is now redundant with the paragraph above
lead = find(lambda l: 'f"Case-level check: {reproduction[\'case_level\'].get(\'joined_cases\', 0):,} cases join on",' in l)
assert '"(network, station, year, realization) and, of those,"' in lines[lead + 1]
lines[lead] = '        "The same cases agree on the numbers themselves only about half the time, so the two"'
lines[lead + 1] = '        "generations are close in distribution and not identical in content:",'
# drop the duplicated blank line that follows the qualification paragraph
blank_run_start = lead
while lines[blank_run_start - 1].strip() == '""':
    blank_run_start -= 1
del lines[blank_run_start + 1 : lead]

# (e) K = 5 caveat after the K table ---------------------------------------
i = find(lambda l: 'f"| {row.k_matched} | {row.n_paired:,} | {_fmt(row.point_c)} | {_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"' in l)
lines.insert(
    i + 2,
    '        "One cell is an exception and is reported as such: K = 5 (n = 450) has an interval that",',
)
lines.insert(
    i + 3,
    '        "includes zero (0.0788 C, -0.0178 to 0.1234). It is the smallest cell above K = 4 and it does",',
)
lines.insert(
    i + 4,
    '        "not change the pooled, rule-level or stratum-level conclusions; the K = 1 to 3 cells, which",',
)
lines.insert(i + 5, '        "carry most of the weight, are all clearly positive.",')

# (f) sign-share sentence ---------------------------------------------------
i = find(lambda l: 'f"The sign is positive in {100 * share_positive:.1f}% of matched pairs.",' in l)
lines[i] = '        f"The sign is positive in {100 * share_positive:.1f}% of matched pairs; the distribution section above shows",'
lines.insert(i + 1, '        "that the mean is carried by the upper tail, not by the typical pair.",')

# (g) stratified identity ---------------------------------------------------
i = find(lambda l: 'f"**+{_fmt(stratified.point_c, 4)} C (95% CI {_fmt(stratified.ci_low_c, 4)} to {_fmt(stratified.ci_high_c, 4)})**,"' in l)
lines[i] = '        f"**+{_fmt(primary_top.point_c, 4)} C (95% CI {_fmt(primary_top.ci_low_c, 4)} to {_fmt(primary_top.ci_high_c, 4)})** on the matched pairs,",'
lines.insert(
    i + 1,
    '        f"with the stratum-weighted estimator (arm x overlap class x K) returning the identical",',
)
lines.insert(
    i + 2,
    '        f"{_fmt(stratified.point_c, 4)} C: within the matched sample there is no residual composition",',
)
lines.insert(i + 3, '        "confounding left for the stratification to remove. The network-equal mean, which lets each",')
lines.insert(
    i + 4,
    '        f"network speak once instead of once per case, is {_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'point_c\'].iloc[0]), 4)} C",',
)
lines.insert(
    i + 5,
    '        f"({_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'ci_low_c\'].iloc[0]), 4)} to {_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'ci_high_c\'].iloc[0]), 4)}), so no single network carries the result.",',
)

# (h) recommended manuscript edit ------------------------------------------
i = find(lambda l: '"## Method notes",' in l)
section = [
    '        "## Recommended manuscript edit",',
    '        "",',
    '        "The published sentence (paper/wrr/wrr_manuscript.tex lines 630-636, and the same text in",',
    '        "wrr_manuscript_published.tex lines 632-638) reads \\"Halving the donor set by training-period",',
    '        "correlation while holding the count fixed costs $+0.082^{\\\\circ}$C (95% interval 0.061 to 0.112)\\"."',
    '        "Under this amendment the count really is held fixed, and the numbers become:",',
    '        "",',
    '        f"- donor-quality contrast: **+{_fmt(primary_top.point_c, 4)} C, 95% interval {_fmt(primary_top.ci_low_c, 4)} to {_fmt(primary_top.ci_high_c, 4)}**",',
    '        f"  (n = {int(primary_top.n_paired):,} matched pairs, {int(primary_top.n_networks)} networks, network-clustered bootstrap,",',
    '        "  2000 draws, seed 0), from `contrasts_matched.csv` row `spec=matched_exact_k`,"',
    '        "  `selection_rule=top_of_half`; cite this amendment and its generation id.",',
    '        f"- donor-shuffle contrast, unchanged in design: +{_fmt(shuffle_full.point_c, 4)} C ({_fmt(shuffle_full.ci_low_c, 4)} to {_fmt(shuffle_full.ci_high_c, 4)})",',
    '        "  on the recomputed sample, against 0.2343 (0.1636 to 0.2881) frozen. The point estimate agrees;",',
    '        "  the interval is wider, so if the whole Step-5 table is regenerated the shuffle interval should",',
    '        "  be refreshed from the same generation rather than mixed with the frozen one.",',
    '        "- if the authors prefer to keep quoting a sample defined exactly as the frozen one did (all four",',
    '        f"  arms finite), the matched number there is +{_fmt(matched_complete_case.point_c, 4)} C"',
    '        f" ({_fmt(matched_complete_case.ci_low_c, 4)} to {_fmt(matched_complete_case.ci_high_c, 4)}).",',
    '        "",',
]
lines[i:i] = section

p.write_text("\n".join(lines) + "\n")
print("patched final polish")
