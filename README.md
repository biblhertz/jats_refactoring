# jats_refactoring

Scripts for processing JATS articles at two different moments of Bibliotheca Hertziana's
editorial workflow. They're independent tools, not a chained pipeline — each runs on its own,
well after the other, on the same article as it moves through editing.

## What's here

| Folder | When it's used | What it does |
|---|---|---|
| [`jats+csl_json`](./jats+csl_json) | Early — right after Sciflow export | **Current.** `refactor_v2.py` fixes Sciflow's JATS ref-list against a Zotero **Better CSL JSON** export — reclassifies titles, rebuilds labels, injects dropped editors, flags duplicates/dangling xrefs/mismatches for human review. Start here. |
| [`jats2indesign`](./jats2indesign) | Late — at final typesetting | Converts the finished JATS article plus a BibTeX bibliography into InDesign-ready XML (via an intermediate HTML/XSLT step), for layout in the journal's master page. Runs independently of the ref-list fix above; there's ordinary editorial work on the article in between. |

An earlier BibTeX-based iteration of the ref-list repair tool (`jats+bibtex`) was retired on
the `v2` branch — fully superseded by `jats+csl_json`. It's still recoverable from git
history (`main` branch / earlier commits) if ever needed for reference.

## Funding

Development of these tools was made possible by a grant from the Deutsche Forschungsgemeinschaft (DFG) — Project number [501142032](https://gepris.dfg.de/gepris/projekt/501142032).

## License

MIT — see [`LICENSE`](./LICENSE).
