# Step 4 decision — demote undeployed support-location uncertainty

**Date:** 2026-10-14  
**Locked science baseline:** `53c88cc`  
**Decision:** **Demote** support-width / support-location uncertainty from claimed method innovation.

## Why (evidence-aligned)

1. The deployed screen still uses a **fixed 30-day** climatological support feature (`peak_overlap` on the 30-day window). Width-scan AUC advantages (≈60–90 d) were never wired into the frozen certificate used for wave-2.
2. Step 2 showed that even **adding** engineered 30-day `peak_overlap` to a same-capacity generic risk model does **not** improve full-data ranking. Promoting a more elaborate undeployed support-uncertainty layer as a headline innovation would widen the method–evidence gap the referee criticised.
3. Proposition-table failure narrowing for C3: if uncertainty handling is not deployed and shown to improve **admission/abstention**, it must not carry end-to-end novelty.

## What stays in the paper

| Content | Role after demotion |
|---|---|
| Fixed 30-day support / peak-overlap | Transparent rule baseline + feature in (or beside) the risk screen; interpretability |
| Width-scan / dilated-window AUC curves | **SI / applicability boundary**: when a wider conditioning window helps risk *discrimination*, without claiming the deployed method uses it |
| “Support-location uncertainty handling” as verified design | **Removed** from abstract, highlights, and contribution list |

## What would reverse this decision

Re-open Step 4 only if a train-only adaptive or probability-weighted support rule is:

1. inserted into the screened pipeline,
2. compared under the same backend risk model to fixed 30-d and a wrong-season negative control,
3. shown to improve OP-70 or OP-RISK5 / abstention on held-out nets (not only AUC or localisation).

Until then, manuscript language must match the deployed object: **fixed-window support features + fitted risk ranking**, not “validated support-uncertainty design.”

## Manuscript edit checklist

- [ ] Abstract / highlights: delete or hedge any claim that support-position uncertainty is a delivered method component
- [ ] §4.3.1 / Table 7: label width scan as exploratory conditioning analysis; state deployed feature remains 30-d
- [ ] Discussion: do not let width-scan AUC substitute for end-to-end admission gains
- [ ] Contributions bullet: replace “support uncertainty” with “indicator-conditioned risk ranking vs seasonal rules” (per Step 2)
