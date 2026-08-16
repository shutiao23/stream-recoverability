# Plain Language Summary

Rivers are often monitored every day for water temperature, flow, and water level. Those records still contain gaps: a sensor can fail for days, several variables at one site can drop out together, or neighbouring stations can go offline at the same time. Filling those gaps is not the same problem as predicting a few randomly missing points, because the useful information that remains depends on how long the gap lasts and on which other measurements are still working.

This study asks when daily stream temperature at three stations on the upper Jinsha River can still be reconstructed under those structured failures. It compares simple interpolation and regression, established neural imputation models, and a model that is allowed to use only the information groups that are actually observed: local history, same-site hydraulics, other stations, and meteorology including satellite shortwave radiation.

The evaluation is locked before performance numbers are read. Model choice is confined to a validation period. Formal tests on a later period, sensitivity versions of the same records, and a separate U.S. river confirmation are not opened until that choice is frozen. This draft therefore reports the locked design, data rights, and audit findings, and it does not claim that any model already beats a baseline.
