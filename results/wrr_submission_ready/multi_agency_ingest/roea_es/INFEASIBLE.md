# ROEA / CEDEX *Anuario de Aforos* (Spain) — INFEASIBLE for the daily transport panel

Verdict: **infeasible**. Retrieved 2026-10-12T10:45:04Z by
`scripts/260_multi_agency_be_es_ingest.py`
(`python3 scripts/260_multi_agency_be_es_ingest.py --provider es`).

The transport protocol needs a **daily river water-temperature** series in °C with a
provider statistic (`MULTI_AGENCY_TRANSPORT_PROTOCOL.md` rules 2–3). The Spanish
national aforo archive publishes **discharge, reservoir, canal, evaporation and
water-quality-sampling** tables, but no water-temperature series. No network is emitted;
nothing was scored.

## 1. Endpoint probe (HTTP evidence)

| URL | HTTP | bytes | transport | note |
|---|---|---|---|---|
| `http://ceh-flumen64.cedex.es/anuarioaforos/` | 500 | 1202 | curl |  |
| `https://ceh.cedex.es/anuarioaforos/default.asp` | 200 | 18271 | curl | <!doctype html> |
| `https://ceh.cedex.es/anuarioaforos/afo/estaf-codigo.asp` | 200 | 4924 | curl | <!DOCTYPE html> |
| `https://ceh.cedex.es/anuarioaforos/Repositorio_Anuarios.asp` | 200 | 9856 | curl | <!DOCTYPE html> |
| `https://ceh.cedex.es/anuarioaforos/api/estaciones` | 403 | 0 | curl |  |
| `https://ceh.cedex.es/anuarioaforos/api/datos` | 403 | 0 | curl |  |
| `https://ceh.cedex.es/anuarioaforos/datos/temperatura` | 403 | 0 | curl |  |
| `https://ceh.cedex.es/roea/` | 200 | 4580 | curl | <!DOCTYPE html> |
| `https://ceh.cedex.es/roea/api/estaciones` | 200 | 4580 | curl | <!DOCTYPE html> |

The demarcación index `https://ceh.cedex.es/anuarioaforos/demarcaciones.asp` was read separately (HTTP 200, 5695 bytes, transport curl).

No data API is exposed. Under `/anuarioaforos/` the `api/` and `datos/` paths answer 403, and
`/roea/` and `/roea/api/estaciones` both return the CHE portal landing page (HTTP 200,
byte-identical 4,580-byte soft 404) rather than data. The site serves an ASP/HTML download
tree plus per-demarcación CSV packages. Python's OpenSSL cannot complete the TLS handshake
with `ceh.cedex.es` (`SSL: UNEXPECTED_EOF_WHILE_READING`); those probes were repeated with the
system `curl`, and the transport column records which client produced each answer.

## 2. Published data files (variable census)

Distinct file names found on the per-demarcación download pages (`<DEMARCACION>_csv.asp`):

| file | demarcaciones publishing it |
|---|---|
| `CANTABRICO.rar` | 1 |
| `DUERO.rar` | 1 |
| `Descripción_Tablas_Mto.pdf` | 10 |
| `EBRO.rar` | 1 |
| `GALICIA COSTA.rar` | 1 |
| `GUADALQUIVIR.rar` | 1 |
| `GUADIANA.rar` | 1 |
| `JUCAR.rar` | 1 |
| `MIÑO-SIL.rar` | 1 |
| `SEGURA.rar` | 1 |
| `TAJO.rar` | 1 |
| `afliq.csv` | 10 |
| `afliqc.csv` | 10 |
| `afliqci.csv` | 10 |
| `afliqe.csv` | 10 |
| `afliqi.csv` | 10 |
| `anual_a.csv` | 10 |
| `anual_c.csv` | 10 |
| `anual_e.csv` | 10 |
| `canal.csv` | 10 |
| `cdr.csv` | 10 |
| `embalse.csv` | 10 |
| `estadis_a.csv` | 10 |
| `estadis_ca.csv` | 10 |
| `estadis_en.csv` | 10 |
| `estadis_enoc.csv` | 10 |
| `estadis_re.csv` | 10 |
| `estadis_sa.csv` | 10 |
| `estaf.csv` | 10 |
| `estev.csv` | 10 |
| `evap.csv` | 10 |
| `extremos_a.csv` | 10 |
| `extremos_a_v.csv` | 10 |
| `gr_cuenca.csv` | 10 |
| `hojas50.csv` | 10 |
| `mensual_a.csv` | 10 |
| `mensual_a_v.csv` | 10 |
| `mensual_c.csv` | 10 |
| `mensual_e.csv` | 10 |
| `muni.csv` | 10 |
| `prov.csv` | 10 |

File families (Anuario de Aforos 2021-2022 edition): `afliq*` aforos líquidos
(discharge measurements), `mensual_*`/`anual_*`/`estadis_*` monthly/annual statistics,
`embalse`/`canal`/`evap` reservoir, canal and evaporation tables, `estaf`/`estev` station
catalogues, `gr_cuenca`/`hojas50`/`muni`/`prov` geography. **No temperature table exists.**

File names matching temp/term/calid: `[]`

## 3. Station catalogue columns

`https://ceh-flumen64.cedex.es/anuarioaforos/anuario-2021-2022/EBRO/estaf.csv` (HTTP 200, 78257 bytes):

```
indroea;lugar;comentario;serv;suprest;suprcnc;hoja_id;alti;altimax;naa;naam;naai;num_cuenca;muni_id;xutm;yutm;xutm30;yutm30;long;lat;longwgs84;latwgs84;observ1;observ2;observ3;observ4;observ5;xetrs89;yetrs89;cod_saih
```

temperature column present: **False**

## 4. The Spanish series that do exist (found instead)

Spanish river water temperature is published by the per-confederación SAIH telemetry
systems, not by CEDEX. The only reachable operator with a **provider daily** water
temperature statistic is SAIH Ebro (Confederación Hidrográfica del Ebro):
`https://www.saihebro.com/api/datos-historicos` with `tipoConsolidado=diario`,
`tiposSenal=TEMPA` and a daily CSV column `MEDIA (oC)`. Its coverage is small and is
reported in this directory's `README.md`, `stations.csv` and `ingest.json` (provider
column `saih_ebro`). CEDEX/ROEA itself contributes nothing.

## 5. Reproduction

```bash
python3 scripts/260_multi_agency_be_es_ingest.py --provider es
```

Raw evidence: `results/wrr_submission_ready/multi_agency_ingest/roea_es/raw_cache/evidence.json`
and the cached listing HTML files in the same directory.
