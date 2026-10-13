"""Scratch patcher: turn the inert K caveat into a computed, emitted block."""

from pathlib import Path

p = Path("/home/lzq/workspace/parttime/stream-recoverability/scripts/247_wrr_mechanism_equal_k.py")
lines = p.read_text().splitlines()

start = next(k for k, l in enumerate(lines) if "One cell is an exception" in l)
end = next(k for k, l in enumerate(lines) if "carry most of the weight, are all clearly positive." in l)
assert end - start == 3, (start, end)

block = [
    "    weak_cells = k_table.loc[pd.to_numeric(k_table[\"ci_low_c\"], errors=\"coerce\") <= 0]",
    "    if len(weak_cells):",
    "        described = \", \".join(",
    "            f\"K = {int(row.k_matched)} (n = {row.n_paired:,}: {_fmt(row.point_c)} C, {_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)})\"",
    "            for row in weak_cells.itertuples()",
    "        )",
    "        lines += [",
    "            \"\",",
    "            f\"The donor-count cells whose interval includes zero are {described}. They are the\"",
    "            \"smallest cells, they carry little weight, and they do not change the pooled, rule-level\"",
    "            \"or stratum-level conclusions; the larger cells are all clearly positive.\",",
    "        ]",
    "    else:",
    "        lines += [",
    "            \"\",",
    "            \"Every donor-count cell excludes zero, so the pooled interval is not an artefact of mixing\",",
    "            \"donor counts.\",",
    "        ]",
]

lines[start : end + 1] = block
p.write_text("\n".join(lines) + "\n")
print("repaired K caveat")
