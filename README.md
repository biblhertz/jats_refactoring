# jats_refactoring

Scripts for Bibliotheca Hertziana's JATS publication pipeline: repairing Sciflow's JATS
exports against the Zotero bibliography, and preparing JATS articles/bibliographies for
InDesign.

## What's here

| Folder | What it does |
|---|---|
| [`jats+csl_json`](./jats+csl_json) | **Current.** `refactor_v2.py` fixes Sciflow's JATS ref-list against a Zotero **Better CSL JSON** export — reclassifies titles, rebuilds labels, injects dropped editors, flags duplicates/dangling xrefs/mismatches for human review. Start here. |
| [`jats2indesign`](./jats2indesign) | Separate pipeline: converts a JATS article plus a BibTeX bibliography into InDesign-ready XML (via an intermediate HTML/XSLT step), for final layout. Not part of the ref-list repair workflow above. |

An earlier BibTeX-based iteration of the ref-list repair tool (`jats+bibtex`) was retired on
the `v2` branch — fully superseded by `jats+csl_json`. It's still recoverable from git
history (`main` branch / earlier commits) if ever needed for reference.

## License

MIT — see [`LICENSE`](./LICENSE).
