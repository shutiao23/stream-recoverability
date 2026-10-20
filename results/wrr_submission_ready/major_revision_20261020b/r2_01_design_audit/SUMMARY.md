# R2-01 design audit

## What the three panels contain
            panel        arm  n_cases  n_station_years  n_stations  n_networks  median_longest_run  mean_n_runs  share_single_run  median_missing_fraction  share_of_panel
      development        all    40704             4045         354         110                60.0     1.401361          0.763512                 0.164384        1.000000
      development  empirical    14995             3823         330         102                22.0     2.089496          0.358053                 0.084699        0.368391
      development stratified    25709             4045         354         110                90.0     1.000000          1.000000                 0.245902        0.631609
         external        all    13017             1103         143          49                30.0     1.489591          0.734194                 0.120548        1.000000
         external  empirical     4977             1103         143          49                11.0     2.280490          0.304802                 0.052055        0.382346
         external stratified     8040             1103         143          49                90.0     1.000000          1.000000                 0.245902        0.617654
crossed_mechanism        all     1918              211          24          12                60.0     1.010949          0.992179                 0.164384        1.000000
crossed_mechanism  empirical       19               13           2           1                30.0     2.105263          0.210526                 0.109589        0.009906
crossed_mechanism stratified     1899              211          24          12                60.0     1.000000          1.000000                 0.164384        0.990094

## Correlation of gap length with hidden support (network-clustered 95% interval)
               panel        arm                             pair     n   pearson        lo       hi  n_clusters
         development        all      length_vs_true_hidden_share 40704  0.516153  0.473998 0.551161       110.0
         development        all length_vs_climatological_overlap 40704  0.452524  0.410025 0.490310       110.0
         development  empirical      length_vs_true_hidden_share 14995  0.643320  0.469690 0.748153       102.0
         development  empirical length_vs_climatological_overlap 14995  0.637986  0.451995 0.751110       102.0
         development stratified      length_vs_true_hidden_share 25709  0.392195  0.374835 0.406588       110.0
         development stratified length_vs_climatological_overlap 25709  0.275385  0.263853 0.286494       110.0
            external        all      length_vs_true_hidden_share 13017  0.515422  0.497648 0.532556        49.0
            external        all length_vs_climatological_overlap 13017  0.464998  0.442649 0.485275        49.0
            external  empirical      length_vs_true_hidden_share  4977  0.568016  0.427505 0.665292        49.0
            external  empirical length_vs_climatological_overlap  4977  0.560193  0.416158 0.665617        49.0
            external stratified      length_vs_true_hidden_share  8040  0.368247  0.346239 0.390464        49.0
            external stratified length_vs_climatological_overlap  8040  0.271513  0.245710 0.296722        49.0
   crossed_mechanism        all      length_vs_true_hidden_share  1918  0.142649  0.124615 0.159666        12.0
   crossed_mechanism        all length_vs_climatological_overlap  1918  0.003044 -0.016808 0.029531        12.0
   crossed_mechanism  empirical      length_vs_true_hidden_share    19       NaN       NaN      NaN         NaN
   crossed_mechanism  empirical length_vs_climatological_overlap    19       NaN       NaN      NaN         NaN
   crossed_mechanism stratified      length_vs_true_hidden_share  1899  0.138156  0.117366 0.157702        12.0
   crossed_mechanism stratified length_vs_climatological_overlap  1899 -0.009369 -0.019670 0.000598        12.0
real_calendar_replay        all length_vs_climatological_overlap   418  0.714415  0.443335 0.889662        14.0

## Real calendars: how many independent units stand behind the 418 groups
n_groups                             418
n_source_incomplete_station_years     59
n_target_station_years                67
n_networks                            14

## Target-length x climatological-overlap cells that are empty or sparse
            panel  target_length climatological_overlap_class  n_cases   cell_status
      development             14                         full        0         empty
      development            270                         none        0         empty
      development            270                      partial       58 sparse_(<100)
         external             14                         full        0         empty
         external            270                         none       10 sparse_(<100)
         external            270                      partial       13 sparse_(<100)
crossed_mechanism             14                         none        0         empty
crossed_mechanism             14                      partial        0         empty
crossed_mechanism             14                         full        0         empty
crossed_mechanism            120                         none        0         empty
crossed_mechanism            120                      partial        0         empty
crossed_mechanism            120                         full        0         empty
crossed_mechanism            180                         none        0         empty
crossed_mechanism            180                      partial        0         empty
crossed_mechanism            180                         full        0         empty
crossed_mechanism            270                         none        0         empty
crossed_mechanism            270                      partial        0         empty
crossed_mechanism            270                         full        0         empty

## Figure provenance
   figure_panel                       source_panel  n_cases  n_station_years  n_networks                                arms                                               support_variable  within_station_year_control                                            identification
      Fig. 1a-c                           external    13017             1103          49              stratified + empirical         true hidden share of the true window (outcome-defined)                        False                   conditional grouping of a mixed archive
        Fig. 1d    external + real_calendar_replay    13435             1170          49 stratified + empirical; real replay                                         climatological overlap                        False                                  descriptive distribution
      Fig. 3a-b crossed_mechanism (stratified arm)     1899              211          12                     stratified only design class on the climatological window; true share reported                         True             same station-year, all 9 length x class cells
        Fig. 3c                           external    13017             1103          49              stratified + empirical                                              true hidden share                        False                   conditional grouping of a mixed archive
      Fig. 4a-c crossed_mechanism (stratified arm)     1899              211          12                     stratified only                    reconstruction diagnostics (post-treatment)                        False grouping on an outcome-side variable; not an intervention
Fig. 4d, Fig. 5             external + development    13017             1103          49              stratified + empirical                                             cross-fitted score                        False                         prediction / admission evaluation
