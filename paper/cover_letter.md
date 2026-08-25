# Cover letter (Water Resources Research)

**Manuscript title:** Reservoir-Associated Thermal Structure Predicts Stream-Temperature Recoverability in the Jinsha and Chattahoochee Rivers

**Dear Editors,**

We submit this Research Article for consideration in *Water Resources Research*. The manuscript connects a familiar hydrological consequence of reservoir releases--altered downstream thermal seasonality and persistence--to a different management question: which information remains available to reconstruct a monitoring outage?

The contribution is not a new dam classifier or an imputation-model leaderboard. A train-only covariance heuristic separates synchronous donor information from local boundary memory before recovery models are evaluated. In two detailed river networks, the station immediately below a major dam is uniquely memory-dominated from 14- to 90-day horizons. In a temporally held-out Chattahoochee evaluation, one model selected only from 2021--2022 validation placements is scored unchanged in 2023--2025. At the memory-dominated Buford site its 90- and 180-day skills are -0.380 and -0.300, while four donor-dominated downstream sites retain 180-day skill of 0.555--0.746.

The paper also makes its generalization boundary central. In an independently frozen panel of 335 United States stream-temperature stations, the frozen primary pooled leave-one-ecoregion-out AUC for upstream major-dam presence is 0.407 (95% interval 0.222--0.515). A post-hoc within-fold diagnosis still finds no national skill (mean AUC 0.526) and a region-dependent direction. The indicator declines with distance within regulated watersheds. We therefore present the calculation as a state- and geography-dependent screening heuristic, not an information-theoretic ceiling or causal reservoir effect.

All main performance results include absolute error. Network-failure effects use leave-one-year-out model selection, so no model is chosen on the event it scores. The Jinsha change date is reported as method-sensitive, donor falsification restricts interpretation to shared predictive information, and all post-hoc analyses are labelled explicitly.

The public code-only release contains no restricted observational bytes. The Jinsha hydrological and meteorological inputs are third-party records for which redistribution permission was not established. They will be uploaded to GEMS as confidential Data Files for Peer Review, with complete provenance and rights documentation. We request the editor's approval of this restricted-data exception; the manuscript will not be submitted until that approval and a real archival software DOI have been obtained. Public USGS, NASA, aggregate tables, figures, and analysis code will be preserved in a DOI-bearing repository.

We believe the work fits WRR because it combines observational hydrology, a transparent analytical heuristic, held-out prediction, and monitoring-network implications while directly testing where geographic generalization fails.

The authors declare that the manuscript is not under consideration elsewhere. Author, funding, conflict-of-interest, and suggested-reviewer information will be supplied in GEMS and must match the final title page.

Sincerely,

**[Corresponding author name required]**
**[Affiliation and email required]**
