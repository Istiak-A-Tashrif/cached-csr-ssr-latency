# Paper draft

- `main.tex`: manuscript in ACM `acmart` (`acmsmall`, `review`) for ACM Transactions on the Web.
- `refs.bib`: references, each verified against Crossref, USENIX, arXiv or the RFC Editor.
- `make_figs.py`: builds `figs/*.pdf` and `tables/*.tex` from the committed evaluation outputs in `testbed/results/` (no hand-typed results except the baseline numbers, which come from `testbed/baselines.py` output and are cited in the script).

Build:

```sh
python3 -m venv .venv && .venv/bin/pip install matplotlib==3.9.2 numpy==2.0.2
.venv/bin/python make_figs.py
tectonic main.tex        # or: latexmk -pdf main.tex
```

- `LITERATURE_SEARCH.md`: search log (sources, queries, screening, results).

Open items are marked `\todo{...}` in `main.tex` (author details, search log, artifact URL, AI-use declaration).
