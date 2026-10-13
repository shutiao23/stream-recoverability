"""Scratch patcher: rewrite the reproduction paragraph as one coherent block."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()

start = next(k for k, l in enumerate(lines) if "The unmatched number lands" in l)
end = next(k for k, l in enumerate(lines) if '"## What the +0.08 C mean is made of",' in l)

block = [
    '        f"The unmatched number lands {_fmt(reproduction[\'point_abs_diff_c\'], 4)} C from the frozen generation:",',
    '        f"{_fmt(reproduction[\'recomputed_original_point_c\'])} C against {_fmt(reproduction[\'frozen_point_c\'])} C frozen, on",',
    '        f"{reproduction[\'recomputed_original_n_paired\']:,} cases against {reproduction[\'frozen_n_paired\']:,} frozen.",',
    '        "",',
    '        "That is a statistical reproduction, not a bit-for-bit one, and the gap is itself part of",',
    '        "the provenance finding: the frozen table cannot be regenerated exactly from the committed",',
    '        f"code. Only {reproduction[\'case_level\'].get(\'joined_cases\', 0):,} of the {reproduction[\'frozen_n_cases\']:,} frozen cases share a",',
    '        "(network, station, year, realization) key with this recomputation, which indicates that the",',
    '        "frozen table was produced by a different revision of the pipeline than the one committed —",',
    '        "a revision that, as the probe below shows, could not run this branch at all. Among the cases",',
    '        "that do join,",',
    '        f"{100 * float(reproduction[\'case_level\'].get(\'longest_run_agreement\', float(\'nan\'))):.1f}% have the same outage geometry and",',
    '        f"{100 * float(reproduction[\'case_level\'].get(\'donor_count_agreement\', float(\'nan\'))):.1f}% the same donor counts, and the pre-fix arm errors agree",',
    '        "only about half the time, so the two generations are close in distribution and not identical",',
    '        "in content.",',
    '        "",',
    '        f"The published number is recovered to {_fmt(reproduction[\'point_abs_diff_c\'], 4)} C, far inside the bootstrap",',
    '        f"standard error of {_fmt(unmatched[\'se_c\'], 4)} C, so the sentence is not wrong about the effect; the",',
    '        "artifact is unreproducible as an artifact.",',
    '        "",',
]

lines[start:end] = block
p.write_text("\n".join(lines) + "\n")
print("rewrote reproduction block")
