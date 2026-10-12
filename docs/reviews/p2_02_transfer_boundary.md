# P2-02 closure: the transfer boundary, and why no Chinese basin is in this paper

Blueprint item P2-02 asked for an independent migration case in a different
thermal environment (China, a regulated reach, or a groundwater-dominated
system), with failure conditions written down before the evaluation, and for the
output to be a *transfer boundary and adaptation cost* rather than another dot on
a map.

## What was done

The pre-registered multi-agency transport test
(`results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md`) is the
transfer case. It recruits agencies that took no part in the v17/v18 development
programme, seals their panels before scoring, and reports the frozen
configuration per provider, per climate/hydrologic context and per assurance
stratum, with pre-declared success and failure criteria. The contexts it covers
are boreal/Nordic (SMHI, Sweden), temperate-oceanic (UK Environment Agency,
England) and temperate-oceanic/continental (Hub'Eau, France; with Belgium and
Spain attempted as a hedge). A separate never-used NVE probe is reported as a
secondary, underpowered transfer check because that provider participated in v17
development.

## Why China is not in this paper

1. **No openly licensed daily river-temperature archive was identified** with the
   structure the design needs (station-level daily water temperature, ≥4 complete
   calendar years per station, river-only, multi-station networks for donors).
   The Chinese material the programme once examined — the *China Hydrological
   Yearbook* series and CMA surface-climate products recorded in
   `metadata/data_rights.csv` — is licensed for neither redistribution nor
   derived publication, and adding it here would require a data-access agreement
   and a separate acquisition project.
2. **A one-station case would not be a transfer test.** The method conditions on
   donors and calibrates at network level, so a single Chinese station cannot
   test it; the design floor in the protocol is ≥30 networks in ≥3 contexts for a
   reason.
3. **Re-labelling a European case as "different" would be dishonest.** The
   transport panel's contexts are genuinely different from the development
   panel's mix, but they are still temperate/boreal and largely
   Atlantic/continental European. They do not substitute for a monsoon-driven,
   heavily regulated, or tropical system.

## The transfer boundary as it stands

Supported by evidence in this paper: the frozen screen's advantage transfers from
the development panel to never-developed networks in boreal, temperate-oceanic
and temperate-continental rivers, at the pre-registered operating point, under
the assurance-stratum caveats recorded in the transport verdict.

Not supported, and not claimed: monsoon-driven thermal regimes, tropical or
subtropical rivers, heavily regulated reaches where the annual peak is set by
operations rather than weather, groundwater-dominated reaches whose seasonal
phase differs from the donor pool, and any archive whose native statistic is not
a daily mean (see the provider strata). A reader applying the method there should
treat the calibration as untested and re-calibrate on their own networks before
using an admission bound.

Adaptation cost, from the transport work: the method needs ≥2 stations per river
system with ≥4 complete years, a station-level donor pool, and a decision-time
climatology; where those exist, the run cost is one calibration per network
group. Where they do not, the honest fallback is the length rule with its known
blind spot for the peak window, not this screen.
