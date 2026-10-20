# Decision information retained after magnitude abstention

This addition is declared before new calibration and test errors are computed.
It implements the review's requirement to specify what information a refused
record can still provide. H30-magnitude admission and a hot-year judgement are
different outputs and their retention rates must not be conflated.

For a fully observed consecutive window, its mean is at most the maximum over
all windows in the complete-record reference. Therefore the maximum over fully
observed windows is a lower bound L on complete-record H30, regardless of what
is missing elsewhere. If L exceeds the declared hot threshold, the hot label is
already identified from observations. A mean based on 24 of 30 days is not a
valid lower bound and is never used here. If no full window exists L is minus
infinity, and no observed-only judgement is made. L below the threshold cannot
establish a cool year.

For every screened magnitude policy, add a secondary downstream policy that
retains an observationally resolved hot label even if the magnitude was
refused. The magnitude admission mask and its 0.5-degree error event remain
unchanged. Report rescued labels, their errors against the complete-record
reference, classification abstentions and the complete-candidate cost. Relative
to the identical original screen, rescuing such a label cannot add a
classification error in this experiment and reduces abstention cost whenever
the declared cost is positive. It need not beat reconstructing all records.
Whether enough labels are rescued to matter is an empirical question.

This is a deterministic relation between the observed and complete recorded
series, not a statement that instruments measure physical temperature without
error. Report fixed 0.1- and 0.2-degree observation-margin sensitivities in
addition to the recorded-reference calculation. These margins are scenarios,
not provider-certified error bounds. The primary H30 error endpoint and the
original H1/H2/H3 comparisons remain unchanged; this decision extension is
reported separately and cannot be used to redefine a failed primary hypothesis.
