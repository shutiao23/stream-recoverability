# P0-04 environment lock note

- Frozen certificate trained/pickled under scikit-learn **1.2.2** (current load succeeds when PYTHONPATH=src and sklearn==1.2.2).
- `constraints.txt` pins **scikit-learn==1.7.2**, which is known to break loading HistGradientBoosting pinball unpickling across major versions.
- Fix: pin the reviewer/reproduction environment to the freeze identity (1.2.2), or re-export the certificate with a supported persistence format without changing predictions. Do **not** silently retrain.
