#!/usr/bin/env python3
"""Independent re-read of every plotted value in figures/wrr/f2_heterogeneity_data.json.

Deliberately does not import scripts/267_wrr_heterogeneity_figures.py: the values
are re-extracted from the artifacts with the stdlib (csv / json) so that a
mistake in the figure script cannot verify itself. Read-only.

    python3 scratch/heterogeneity/verify_sources.py
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON = ROOT / "figures" / "wrr" / "f2_heterogeneity_data.json"
SCRATCH = ROOT / "scratch" / "heterogeneity"

failures: list[str] = []
checks = 0


def close(a, b, tol=1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def expect(label: str, got, want) -> None:
    global checks
    checks += 1
    if isinstance(want, float) or isinstance(got, float):
        ok = close(got, want, 1e-9)
    else:
        ok = got == want
    if not ok:
        failures.append(f"{label}: json={got!r} artifact={want!r}")


def rows_of(rel: str) -> list[dict]:
    with (ROOT / rel).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


payload = json.loads(JSON.read_text(encoding="utf-8"))

# ---- panel a -------------------------------------------------------------- #
auc = {row["metric"]: row for row in rows_of("results/v17_fitness/step22_robustness/auc_contrasts.csv")}
for row in payload["panel_a"]["rows"]:
    src = auc[row["metric"]]
    for key, field in (
        ("auc_timing_minus_length", "auc_timing_minus_length"),
        ("ci_low", "ci_low"),
        ("ci_high", "ci_high"),
        ("tolerance_c", "tolerance_c"),
        ("base_rate", "base_rate"),
    ):
        expect(f"panel a {row['metric']} {key}", row[key], float(src[field]))
    expect(f"panel a {row['metric']} n_cases", row["n_cases"], int(src["n"]))

# ---- panel b -------------------------------------------------------------- #
arms = {
    (row["panel"], row["arm"]): row
    for row in rows_of("results/v17_fitness/step11_arm_robustness/arm_contrasts.csv")
}
step10 = load("results/v17_fitness/step10_confirmation/verdict.json")
sealed = load("results/wrr_submission_ready/p0_07_sealed_confirmation/verdict.json")
diagnostic = load(
    "results/wrr_submission_ready/amendments/sealed_usgs_prior_access_diagnostic/summary.json"
)
transport = load("results/wrr_submission_ready/p0_07b_multi_agency_transport/verdict.json")

by_label = {row["label"].strip(): row for row in payload["panel_b"]["rows"]}

dev = by_label["v17 development, pooled"]
expect("dev point", dev["estimate_points"], float(arms[("development", "pooled")]["contrast_points"]))
expect("dev low", dev["ci_low_points"], float(arms[("development", "pooled")]["ci_low_points"]))
expect("dev high", dev["ci_high_points"], float(arms[("development", "pooled")]["ci_high_points"]))
expect("dev n", dev["n_cases"], int(arms[("development", "pooled")]["n_cases"]))

res = by_label["v17 reserved, pooled"]
expect("res point", res["estimate_points"], float(step10["primary"]["contrast_points"]))
expect("res low", res["ci_low_points"], float(step10["primary"]["ci_points"][0]))
expect("res high", res["ci_high_points"], float(step10["primary"]["ci_points"][1]))
expect("res n", res["n_cases"], int(step10["n_cases"]))
expect("res nets", res["n_networks"], int(step10["n_networks"]))
expect("res cross-check point", res["cross_check"]["estimate_points"],
       float(arms[("reserved", "pooled")]["contrast_points"]))

pooled = by_label["Sealed USGS, pooled"]
expect("sealed pooled point", pooled["estimate_points"], float(sealed["contrast_points"]))
expect("sealed pooled low", pooled["ci_low_points"], float(sealed["ci_low_points"]))
expect("sealed pooled high", pooled["ci_high_points"], float(sealed["ci_high_points"]))
expect("sealed pooled n", pooled["n_cases"], int(sealed["n_cases"]))
expect("sealed pooled nets", pooled["n_networks"], int(sealed["n_networks"]))

emp = by_label["Sealed USGS, empirical arm"]
expect("sealed emp point", emp["estimate_points"],
       float(sealed["by_arm_points"]["empirical"]["contrast_points"]))
expect("sealed emp low", emp["ci_low_points"],
       float(sealed["by_arm_points"]["empirical"]["ci_low_points"]))
expect("sealed emp high", emp["ci_high_points"],
       float(sealed["by_arm_points"]["empirical"]["ci_high_points"]))

clean = by_label["Sealed USGS, clean subset"]
clean_src = next(
    row for row in diagnostic["rows"] if row["subset"] == "networks_clean_of_outcome_use"
)
expect("clean point", clean["estimate_points"], float(clean_src["pooled_contrast_points"]))
expect("clean low", clean["ci_low_points"], float(clean_src["pooled_ci_low_points"]))
expect("clean high", clean["ci_high_points"], float(clean_src["pooled_ci_high_points"]))
expect("clean n", clean["n_cases"], int(clean_src["n_cases"]))
expect("clean nets", clean["n_networks"], int(clean_src["n_networks"]))

primary = by_label["Transport, primary panel"]
expect("transport primary point", primary["estimate_points"],
       float(transport["primary_panel"]["contrast_points"]))
expect("transport primary low", primary["ci_low_points"],
       float(transport["primary_panel"]["ci_low_points"]))
expect("transport primary high", primary["ci_high_points"],
       float(transport["primary_panel"]["ci_high_points"]))
expect("transport primary n", primary["n_cases"], int(transport["primary_panel"]["n_cases"]))
expect("transport primary nets", primary["n_networks"], int(transport["primary_panel"]["n_networks"]))

for key, label in (("smhi", "SMHI"), ("uk_ea", "UK EA"), ("hubeau", "Hub'Eau")):
    row = by_label[label]
    src = transport["by_provider_points"][key]
    expect(f"{label} point", row["estimate_points"], float(src["contrast_points"]))
    expect(f"{label} low", row["ci_low_points"], float(src["ci_low_points"]))
    expect(f"{label} high", row["ci_high_points"], float(src["ci_high_points"]))
    expect(f"{label} n", row["n_cases"], int(src["n_cases"]))
    expect(f"{label} nets", row["n_networks"], int(src["n_networks"]))

nve = by_label["Transport, NVE secondary"]
expect("nve point", nve["estimate_points"], float(transport["secondary_panel"]["contrast_points"]))
expect("nve low", nve["ci_low_points"], float(transport["secondary_panel"]["ci_low_points"]))
expect("nve high", nve["ci_high_points"], float(transport["secondary_panel"]["ci_high_points"]))
expect("nve n", nve["n_cases"], int(transport["secondary_panel"]["n_cases"]))
expect("nve nets", nve["n_networks"], int(transport["secondary_panel"]["n_networks"]))

expect("threshold", payload["conventions"]["threshold_points"],
       float(transport["predeclared_rule"]["delta_points"]))

# ---- drawn values match the recorded model -------------------------------- #
# The plotted coordinates are the JSON values themselves; re-assert the two
# orderings the panels claim.
panel_a_values = [row["auc_timing_minus_length"] for row in payload["panel_a"]["rows"]]
expect("panel a sorted descending", panel_a_values == sorted(panel_a_values, reverse=True), True)
panel_a_nets = {row["n_networks"] for row in payload["panel_a"]["rows"]}
expect("panel a network count single-valued", panel_a_nets, {110})

first_provider = min(
    (row for row in payload["panel_b"]["rows"] if row["label"].strip() in ("SMHI", "UK EA", "Hub'Eau")),
    key=lambda row: ["smhi", "uk_ea", "hubeau"].index(row["provider"]),
)
expect("transport has three primary providers",
       sorted(row["provider"] for row in payload["panel_b"]["rows"] if "provider" in row),
       ["hubeau", "smhi", "uk_ea"])

# ---- artifacts unchanged since the build ---------------------------------- #
import hashlib  # noqa: E402

for record in payload["artifacts"]:
    digest = hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest()
    expect(f"sha256 {record['path']}", digest, record["sha256"])

# ---- independent PDF checks ----------------------------------------------- #
REPORT = {}
for name in ("f2a_endpoint_ordering", "f2b_panel_heterogeneity"):
    pdf = ROOT / "figures" / "wrr" / f"{name}.pdf"
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    fonts = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, check=True).stdout
    bbox = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"], capture_output=True, text=True, check=True
    ).stdout
    pages = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
    size = re.search(r"^Page size:\s+([\d.]+) x ([\d.]+) pts", info, re.M)
    width_pt = float(size.group(1))
    words = [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5))
        for m in re.finditer(
            r'<word xMin="([\d.eE+-]+)" yMin="([\d.eE+-]+)" xMax="([\d.eE+-]+)" '
            r'yMax="([\d.eE+-]+)">(.*?)</word>',
            bbox,
        )
    ]
    page = re.search(r'<page width="([\d.]+)" height="([\d.]+)">', bbox)
    pw, ph = float(page.group(1)), float(page.group(2))
    outside = [w[4] for w in words if w[0] < -0.01 or w[1] < -0.01 or w[2] > pw + 0.01 or w[3] > ph + 0.01]
    overlaps = 0
    for i in range(len(words)):
        for j in range(i + 1, len(words)):
            dx = min(words[i][2], words[j][2]) - max(words[i][0], words[j][0])
            dy = min(words[i][3], words[j][3]) - max(words[i][1], words[j][1])
            if dx > 0.4 and dy > 0.4:
                overlaps += 1
    heights = sorted(w[3] - w[1] for w in words)
    REPORT[name] = {
        "pages": pages,
        "width_in": round(width_pt / 72, 3),
        "fonts": [line.strip() for line in fonts.splitlines()[2:] if line.strip()],
        "n_words": len(words),
        "outside": outside,
        "overlaps": overlaps,
        "min_box_pt": round(heights[0], 3),
    }
    expect(f"{name} one page", pages, 1)
    expect(f"{name} fits 5.5 in", width_pt / 72 <= 5.5, True)
    expect(f"{name} no word outside page", len(outside), 0)
    expect(f"{name} no overlapping words", overlaps, 0)
    if not all("yes" in line.split()[-5:-2] for line in REPORT[name]["fonts"]):
        failures.append(f"{name}: a font is not embedded: {REPORT[name]['fonts']}")
    checks += 1

(SCRATCH / "verify_report.json").write_text(json.dumps(REPORT, indent=2), encoding="utf-8")

print(f"{checks} checks, {len(failures)} failure(s)")
for failure in failures:
    print(f"  FAIL {failure}")
print(json.dumps(REPORT, indent=2))
sys.exit(1 if failures else 0)
