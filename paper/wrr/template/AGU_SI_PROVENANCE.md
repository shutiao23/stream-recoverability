# AGU supporting-information class provenance

The current supplement uses `agutexSI2019.cls`, dated January 14, 2019, named in the [AGU LaTeX submission guidelines](https://www.agu.org/-/media/files/publications/latex_submission_guidelines_jan162023.pdf). AGU's [current supporting-information instructions](https://www.agu.org/publications/authors/journals/supporting-information) link to the supporting template and require text, captions and figures in one PDF. The official ZIP linked from the current author page returned HTTP 403 during this retrieval on 2026-10-27; this file was therefore obtained from two public mirrors. It is not claimed to be independently authenticated against a successful current publisher ZIP download.

The mirrors returned byte-identical files with Git blob `c700b48de3f65d67a50e1041bd070da4d9be91f2`:

- [CLM5_FACE_EXPTS class](https://github.com/rosiealice/CLM5_FACE_EXPTS/blob/master/agutexSI2019.cls)
- [AGUTeX article class mirror](https://github.com/jacgraz/AGU-Geophysical-Research-Letters-AGUTeX-Article/blob/main/agutexSI2019.cls)

Local SHA-256: `2ae0ca95220db0c82523e20963061aa0958c79c9e3d2bcd1957e844308de5908`. The class is unmodified and retains the authorship and copyright notices in its header. The project's MIT licence does not replace those third-party notices or grant rights over the template.

The document wrapper selects `draft,wrr`, uses the SI title/article structure, and restores the class's saved standard LaTeX float/tabular interfaces for the existing embedded, resized summary tables. This compatibility setup is in the manuscript wrapper, not a modification to the class. The scientific supplement body and its input declarations were compared byte-for-byte with the preceding version before the format change. All 34 text sections and 40 summary tables are retained; the draft page count changes with layout and spacing. Author metadata remains pending.
