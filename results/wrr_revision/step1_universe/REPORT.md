# Step 1 — evaluation universe and complete-year thermal truth

As of `2026-09-07`. Reference series are not imputed.
The main hottest-30 endpoint is defined only on fully observed calendar years
of river objects. Non-river objects are a transfer population, not part of
the river confirmation average.

## Frozen denominator

- Networks scanned: **284**
- River networks: **269**
- Non-river networks: **15**
- Eligible river complete station-years: **5307**
- Eligible networks / stations: **161** / **547**
- Opened v16 confirmation station-years (development/retrospective only): **413**
- Candidate unseen complete river station-years: **293** on **37** networks

The 846-case river+complete-year confirmation subset already read in the
2026-09-07 review remains development diagnostics. It is not a new unseen
confirmation set.

## v16 confirmation networks previously flagged non-river

`rws_amsterdam_rijnkanaal`, `rws_grevelingen`, `rws_haringvliet`, `rws_ijsselmeer_markermeer`, `rws_noordzee`, `rws_rijn_maas_delta`, `rws_twentekanalen`, `rws_volkerak_krammer`, `rws_waddenzee`, `rws_westerschelde`

## Warm-season vs annual peak on complete years

        evidence_use waterbody_class  n_station_years  n_networks  n_stations  warm_equals_annual_rate  n_warm_complete
    candidate_unseen           river              293          37          59                 0.969283              293
  descriptive_second           river             1553          57         218                 0.987766             1553
  design_development           river             3048          42         225                 0.969816             3048
retrospective_opened           river              413          25          45                 1.000000              413

A warm-season-only year may be used later only if this agreement rate is high on complete years and the endpoint is frozen in advance.

## Exclusion counts

       level                                 reason    n
     network                  waterbody_class=river  269
     network                   waterbody_class=lake    5
     network                  waterbody_class=canal    3
     network                waterbody_class=estuary    3
     network                    waterbody_class=sea    2
     network                waterbody_class=coastal    1
     network          waterbody_class=estuary_delta    1
     network                v16_role=no_temperature  109
     network      v16_role=second_panel_descriptive   57
     network       v16_role=first_panel_development   42
     network            v16_role=unscored_available   40
     network       v16_role=v16_confirmation_scored   36
station_year                               eligible 5307
station_year               incomplete_calendar_year 4031
station_year                       no_observed_days 1989
station_year                         year_not_ended  247
station_year                    non_river_waterbody  225
station_year evidence_use=excluded_from_annual_main 6492
station_year        evidence_use=design_development 3048
station_year        evidence_use=descriptive_second 1553
station_year      evidence_use=retrospective_opened  413
station_year          evidence_use=candidate_unseen  293

## Non-river objects (transfer list, not river main)

                     network_id waterbody_class                v16_role
   ccg_st_lawrence_ship_channel           canal          no_temperature
     eccc_automated_great_lakes            lake          no_temperature
eccc_automated_maritime_coastal         coastal          no_temperature
            ehyd_neusiedler_see            lake          no_temperature
       rws_amsterdam_rijnkanaal           canal v16_confirmation_scored
                rws_grevelingen            lake v16_confirmation_scored
                rws_haringvliet         estuary v16_confirmation_scored
      rws_ijsselmeer_markermeer            lake v16_confirmation_scored
                   rws_noordzee             sea v16_confirmation_scored
              rws_oosterschelde         estuary          no_temperature
            rws_rijn_maas_delta   estuary_delta v16_confirmation_scored
              rws_twentekanalen           canal v16_confirmation_scored
           rws_volkerak_krammer            lake v16_confirmation_scored
                  rws_waddenzee             sea v16_confirmation_scored
              rws_westerschelde         estuary v16_confirmation_scored

## Eligible river complete years by evidence use

        evidence_use  n_networks  n_stations  n_station_years
    candidate_unseen          37          59              293
  descriptive_second          57         218             1553
  design_development          42         225             3048
retrospective_opened          25          45              413
