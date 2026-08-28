# LUBW continuous-temperature source audit

Official source checked on 2026-08-28:

- LUBW's river-data page states that 26 online stations continuously measure
  water temperature and points historical daily means to the official Daten-
  und Kartendienst.
- The official link resolves to the public Cadenza workbook “Daten der
  Online-Messstationen”.
- Its public table request returned HTTP 200 and `rowsTotal=1199435`; the
  returned fields include station, river, parameter, date, value, and unit.
- The same table under the durable repository path without a temporary
  workbook-state identifier returned HTTP 404.
- The working route requires a server-created opaque workbook-state identifier.
  It was retained only in process memory for the duration of the official
  session. It was not written to any output, used as an artifact identity, or
  used to calculate or validate file content.
- The completed official scan returned 131 stations with published daily water
  temperature and 407,257 station-day values. Exact-river grouping produced
  nine candidate networks. Neckar and Rhein passed the common confirmation QC;
  seven groups did not.

Reproduction outline:

1. `GET https://www.lubw.baden-wuerttemberg.de/en/wasser/fliessgewaesserdaten`
2. Follow the official “online-messstationen” Daten- und Kartendienst link.
3. Read the public export-table view from the returned session workbook.
4. Retain published `Temperatur` rows in degrees Celsius and discard all other
   parameters.
5. Compare the working route with the same view under the durable repository
   route without the temporary state identifier (HTTP 404).

No alternative host, mirror, cached temperature value, or unofficial endpoint
was used.
