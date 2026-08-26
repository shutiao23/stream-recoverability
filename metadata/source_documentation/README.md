# Source and provenance notes

The supplied files contain no embedded station names, source identifiers, units, time-zone metadata, or per-value quality flags. The mappings below are therefore documented from independent reconciliation and literature, rather than silently assumed. The still-missing instrument, calibration, quality-code, and interpolation pedigree is listed in `source_provenance_v3.md`. Jinsha remains an exploratory context network until that list is closed.

## Core hydrological stations

- `B1` is Batang (`BT`), `S2` is Shigu (`SG`), and `P3` is Panzhihua (`PZH`). They occur in this upstream-to-downstream order on the Jinsha River.
- Station coordinates and drainage areas come from published station inventories. Batang is reported at 99°05′ E, 29°51′ N with a 187,507 km² drainage area; Shigu at 99°56′52″ E, 26°54′24″ N with 214,184 km²; Panzhihua at 101°44′41″ E, 26°38′19″ N with 259,177 km².
- Daily stream temperature and discharge for these stations are described in the literature as originating in the *Annual Hydrological Report of the People's Republic of China, Volume VI: Hydrological Data of the Changjiang River Basin*.
- The public Figshare record `10.6084/m9.figshare.29002466.v4` independently reproduces the 2006 onward monthly means for Batang and Shigu from daily historical records. Most Batang months agree exactly with the supplied daily aggregation. Shigu agrees through 2012 but has a 2013–2019 year-order discrepancy; this is retained as a provenance limitation rather than silently rewritten.

## Meteorological stations and variables

The first five supplied `TEMP`, `WDSP`, and `PRCP` records match the NOAA Global Summary of the Day station files without ambiguity after converting GSOD `TEMP` from Fahrenheit to Celsius:

- The documented hydrological--meteorological pairings are not co-located. Straight-line haversine distances are 16.756 km (B1--Batang meteorology), 27.890 km (S2--Lijiang), and 50.234 km (P3--Huili); the coordinates, distance method, and values are preserved in `metadata/station_metadata.csv`. Consequently, hiding hydrology and meteorology together is described as a multisource regional-data outage, not a proven single-station communications failure.
- The supplied hydrological files expose calendar dates but no time zone or hydrological-day cutoff. Meteorological reconciliation is consistent with daily GSOD products, whose aggregation convention is documented separately. The workflow aligns the published daily labels without inventing a subdaily conversion, and this unresolved time convention is retained as a limitation.

| Core ID | WMO/GSOD ID | Meteorological station | Coordinates | Elevation |
| --- | --- | --- | --- | ---: |
| B1 | 56247099999 | Batang | 30.00 N, 99.10 E | 2589 m |
| S2 | 56651099999 | Lijiang (`LIJING` in GSOD) | 26.8333 N, 100.2167 E | 2382 m |
| P3 | 56671099999 | Huili | 26.65 N, 102.25 E | 1788 m |

GSOD documents `WDSP` as knots with `999.9` meaning no report, and `PRCP` as inches with `99.99` meaning no report. Processing therefore converts valid wind values by `0.514444` to m/s and precipitation by `25.4` to mm/day.

`RHMEAN` and `DH` are the standard variable names used by China's surface climate daily value dataset V3.0 for mean relative humidity (%) and sunshine duration (h), respectively. `DH` is therefore not used as an unidentified feature. In the v2 executable freeze, Jinsha `DH` sunshine hours are a sensitivity-only channel. The main Group D meteorology channel on both networks is `Rs` (NASA POWER `ALLSKY_SFC_SW_DWN`, MJ/m²/day). Do not treat confirmatory shortwave as sunshine duration under the name `DH`.

## Known limitations

- The supplied CSVs do not include the original hydrological or meteorological quality-code columns.
- No source statement found during the audit says that the supplied daily values were previously imputed. Conversely, the absence of flags means prior interpolation cannot be disproved from the CSVs alone. Results must describe them as published, unflagged values—not raw sensor samples with complete provenance.
- Daily discharge is a published hydrological product and is commonly obtained from stage–discharge measurements/rating procedures. The within-year numerical relationship is nearly deterministic at all three stations. B1 has an approximately 8.48 m water-level datum step between 2018-12-31 and 2019-01-01 without a corresponding discharge jump, which depresses its full-period correlation. FLOW and WLEVEL are therefore treated as one hydraulic information group in independence analyses, and the B1 datum step is retained and reported rather than silently adjusted.
- No additional public daily stream-temperature series with comparable coverage was found. The expanded-network claim is therefore not made; leave-one-station-out analysis is exploratory within a three-station case study.

## References consulted

- NOAA GSOD format and missing-code documentation: https://www.ncei.noaa.gov/data/global-summary-of-the-day/
- China surface climate daily value dataset V3.0 portal: http://data.cma.cn/
- Wei et al. data and code record (CC BY 4.0): https://doi.org/10.6084/m9.figshare.29002466.v4
- Wei et al., *Flow composition mediates the sensitivity to air temperature of streams in a Qinghai-Tibetan watershed*: https://www.nature.com/articles/s43247-026-03340-2
- Wang et al., *Analysis of Water Temperature Variations in the Yangtze River's Upper and Middle Reaches*: https://doi.org/10.3390/w16121669
- Station inventory for Shigu and Panzhihua: https://doi.org/10.1007/s11629-018-4924-3
- Published Zhimenda station coordinates and drainage area: https://doi.org/10.1007/s11629-014-3180-4
- Gangtuo candidate coordinate proxy (river sampling site): https://pmc.ncbi.nlm.nih.gov/articles/PMC12984315/
- Benzilan candidate coordinate proxy (river sampling site): https://doi.org/10.3390/ani12233412
