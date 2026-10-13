"""Scratch patcher: rewrite the verdict paragraph and restore a blank line."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()

start = next(k for k, l in enumerate(lines) if "The claim was: quality, not quantity, drives the residual" in l)
end = next(k for k, l in enumerate(lines) if k > start and l.strip() == "]" )

block = [
    '        "The claim was: quality, not quantity, drives the residual, and halving the donor",',
    '        "set by correlation while holding the count fixed costs about +0.08 C. Under exact",',
    '        "matching on donor count, on arm and on overlap class, the contrast is",',
    '        f"**+{_fmt(primary_top.point_c, 4)} C (95% CI {_fmt(primary_top.ci_low_c, 4)} to {_fmt(primary_top.ci_high_c, 4)})** on the matched pairs.",',
    '        "Under the three admissible within-half selection rules it spans",',
    '        f"{_fmt(primary[\'point_c\'].min(), 4)} to {_fmt(primary[\'point_c\'].max(), 4)} C; the weakest of the three (`{weakest_rule}`) gives",',
    '        f"{_fmt(weakest.point_c, 4)} C ({_fmt(weakest.ci_low_c, 4)} to {_fmt(weakest.ci_high_c, 4)}), still excluding zero.",',
    '        f"The stratum-weighted estimator (arm x overlap class x K) returns the identical {_fmt(stratified.point_c, 4)} C, so",',
    '        "no composition confounding is left inside the matched sample for the stratification to remove,",',
    '        f"and the network-equal mean is {_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'point_c\'].iloc[0]), 4)} C",',
    '        f"({_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'ci_low_c\'].iloc[0]), 4)} to {_fmt(float(contrasts.loc[contrasts[\'spec\'] == \'matched_exact_k_network_equal\', \'ci_high_c\'].iloc[0]), 4)}), so no single network carries the result.",',
    '        f"The sign is positive in {100 * share_positive:.1f}% of matched pairs; the distribution section above",',
    '        "shows that the mean is carried by the upper tail, not by the typical pair.",',
    '        "",',
]
lines[start:end] = block

# blank line before the shuffle heading
i = next(k for k, l in enumerate(lines) if l.strip() == '"## The shuffle control in the same table",')
if lines[i - 1].strip() != "lines += [":
    lines.insert(i, '        "",')

p.write_text("\n".join(lines) + "\n")
print("rewrote verdict paragraph")
