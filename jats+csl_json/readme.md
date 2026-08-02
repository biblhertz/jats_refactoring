# refactor_v2.py — Sciflow → JATS ref-list repair tool (JATS + CSL-JSON)

Fixes the structural and data-loss problems in Sciflow's JATS export before it goes through
manual `element-citation` → `mixed-citation` conversion for Bibliotheca Hertziana
publications. Takes a Sciflow XML export and a Zotero **Better CSL JSON** export as input,
and produces a corrected ref-list plus a report of everything it changed or flagged.

This supersedes an earlier BibTeX-based pipeline, retired on this branch — see
[§7](#7-relationship-to-the-retired-bibtex-based-pipeline) for what changed and why.

## Why this exists

Sciflow's JATS export has a number of known, recurring problems that would otherwise have to
be fixed by hand, per article, every time:

- `<article-title>` used regardless of publication type (should be `<source>` for books,
  `<part-title>` for chapters/conference papers/dictionary entries)
- Editors/contributors silently dropped from `<element-citation>` even when they're present
  in the source Zotero record
- `<label>` is always a bare incrementing number, never a usable citation label
- Manuscripts and other archival items get miscategorized as `publication-type="preprint"`
- `publisher-loc` sometimes gets contaminated with a conference's `event-place` instead of
  the actual place of publication
- Citation keys with capital roman numerals (e.g. `documentiIII1880`) get silently lowercased
  by Sciflow, breaking exact-match lookups against the Zotero export
- Citations can exist in the article body with no corresponding `<ref>` in the ref-list at
  all (never added to the bibliography, or added to Zotero but filed outside this article's
  export collection)
- Two Zotero records sharing a citation-key stem but differing only by a disambiguating
  letter suffix (e.g. `russo2012a`/`russo2012b`) can, in principle, get collapsed onto the
  same `<ref>` id with duplicated content — though the same symptom can also be a harmless
  stale duplicate left over from re-exporting after a Zotero-side merge. The tool checks the
  body's own citation text to tell these apart rather than assuming the worse case.

None of these are edge cases — they show up in essentially every article. This tool exists
to fix the mechanical ones automatically and clearly flag the ones that need a human decision,
so the manual conversion step starts from a much cleaner baseline.

## 1. Requirements

- Python 3.9+
- One package: `lxml`
  ```
  pip install lxml --break-system-packages
  ```
  (drop `--break-system-packages` if you're in a virtualenv)

## 2. The two input files you need

1. **The Sciflow JATS export** — the full article XML, containing the `<body>` (with all
   the in-text `<xref ref-type="bibr">` citations) and the `<back><ref-list>` (with all the
   `<ref>` entries).

2. **Better CSL JSON** — exported from Zotero using the **Better CSL JSON** translator
   specifically (not plain "CSL JSON," not BibTeX, not RDF). This is the one that correctly
   flattens Extra-field keys (`note`, `genre`, `event-place`, `event-date`) and gives clean
   `family`/`given` name arrays. If you're not sure which translator produced a given file,
   check the `note` field of any exhibition-catalogue-type record: if it's one clean sentence,
   you have Better CSL JSON; if it's several `key: value` lines jammed together with `\n`,
   you exported the wrong thing and need to redo it.

Both files need to be on the same machine/session where you run the script — it does not
fetch anything, it only reads these two local files.

## 3. Running it

```
python3 refactor_v2.py path/to/article.xml path/to/library.json
```

Or run it with no arguments and it'll prompt you for both paths.

It writes four files next to your input XML (say your input was `article.xml`):

| File | What it is |
|---|---|
| `article_fixed.xml` | The main Bibliografia ref-list, fixed and sorted (see §4) |
| `article_manuscripts.xml` | Manuscript-type refs split into their own `<ref-list>`, fixed, sorted, but NOT restructured (shelfmark/title still needs manual cleanup - see §4) |
| `article_enrichment.json` | Per-ref `note`/`genre`/`event-*`/`abstract`/`collection-*` fields that Sciflow drops entirely — kept here so nothing is lost before the later mixed-citation step |
| `article_report.md` | Everything the script did, everything it flagged, and everything it confirmed but left untouched — read this first |

**Nothing is overwritten in place.** Your original XML is never modified — always work from
the `_fixed.xml`/`_manuscripts.xml` copies.

## 4. What it actually does (and does NOT do)

**Fixes automatically, in the XML:**
- Reclassifies `<article-title>` to `<source>`/`<part-title>` based on the CSL-JSON's own
  `type` field (not whatever Sciflow's XML attribute says)
- Replaces numeric `<label>` values with a real label:
  - author-year for records with a real `author`
  - `title-short` (+ year, unless the year is already baked into title-short) for
    no-author/reference-corpus items (exhibition catalogues, DBI/EAA/LIMC/AGD-style works)
  - shelfmark/`title-short` alone for manuscripts
  - `"[untitled] vol. N, year"` as a last resort when there's no author, no editor, and no
    title-short at all — deliberately ugly, meant to be impossible to miss, and specifically
    designed to avoid two different volumes of the same set silently colliding on a bare year
- Syncs every `<xref rid="...">` in the body to match the new label (never touches anything
  else in the surrounding text - see the verification behavior below)
- Injects missing `<person-group>` (author/editor) from the JSON when Sciflow dropped it -
  institutional/literal names go into `<collab>`, not `<name>`
- Fixes `publisher-loc` when it looks like it was contaminated with `event-place`
- Inserts missing `fpage`/`lpage` when the XML has neither
- **Matches refs to JSON records case-insensitively as a fallback** when the exact `id` isn't
  found - this specifically covers citation keys with capital roman numerals (e.g.
  `documentiIII1880`), since Sciflow lowercases everything in the `ref/@id` it generates while
  Zotero/BetterBibTeX preserves the case you typed. Logged separately as routine, not as
  something needing review (see the report-bucket list below).
- **Sorts both ref-lists alphabetically by the corrected label** - diacritic-normalized for
  comparison only (so "Chłedowski" sorts where "Chledowski" would), but leading articles are
  NOT stripped ("L'istante..." sorts under "L" - if you want it to sort under "I," change the
  `title-short` itself, the script won't guess). Manoscritti and Bibliografia use the exact
  same sort rule. This sort always runs last, on the corrected labels - never on the original
  numeric ones.

**Flags in the report, but never auto-changes:**
- **Duplicate `<ref>` ids** — two `<ref>` elements sharing the exact same `@id`. When
  `element-citation` content is also identical, there are two distinct possible causes and
  the script reports which is more likely rather than assuming the alarming one:
  1. **Content loss** — two genuinely different Zotero records shared a citation-key stem,
     differing only by a disambiguating letter suffix (e.g. `russo2012a`/`b`); Sciflow
     stripped the suffix, both collapsed onto one id, and one record's real content was
     overwritten.
  2. **Benign stale duplicate** — the same reference was cited twice in the body from the
     start (confirmed by checking whether the body's `<xref>`s already agree with each other);
     Zotero once had a genuine duplicate item for it that was later merged into one, but
     Sciflow's ref-list generation left a stale second `<ref>` rather than fully rebuilding.
     Nothing is lost here — one copy can simply be deleted.

  The script checks the body's own `<xref>` text as a signal to distinguish these two, but
  always says "confirm against Zotero" rather than deciding for you either way.
- Page-range mismatches between the XML and the JSON (you decide which is right)
- Any ref with no matching JSON record at all (`no_match`)
- **Dangling xrefs** — a citation exists in the body (`<xref rid="X">`) but there is NO
  `<ref id="X">` anywhere in the ref-list at all. Different failure mode from "no JSON match"
  (which requires a `<ref>` to exist in the first place) - this catches citations that were
  never added to the bibliography, or added to Zotero but filed outside this article's export
  collection.
- **Label collisions** — a global pass, after all labels are built, checking whether any two
  refs ended up with the identical final label. Catches cases the per-ref fallback logic can't
  see on its own (e.g. would have caught two undated volumes both collapsing to a bare year,
  before the volume-aware fallback made that specific case self-avoiding).
- **Xref/author-text agreement** — this is a verification aid, not cleanup, and it never edits
  or deletes anything. It compares the xref's own auto-generated link text (and the record's
  `title-short`/shelfmark) against whatever text the author originally typed right after the
  xref, and reports whether they agree, partially agree, or disagree outright. A disagreement
  is a real signal the xref might be attached to the wrong `rid` - it does NOT mean the
  trailing author text is a "duplicate" to be removed. That trailing text is deliberately kept
  as your own verification anchor and the script respects that.
- **Every authored manuscript**, always flagged for target verification - even when this
  specific instance's agreement check passes - because an author-dated manuscript can collide
  with a sibling manuscript by the same author under an author-date label. Manuscripts get
  checked against their shelfmark specifically, which is a much stronger signal than
  author-date agreement for this type.
- **Possible uncited references in figure/table captions** — a narrow, scoped scan inside
  `<fig>`/`<table-wrap>` elements only, looking for plain-text author-year patterns that
  aren't already wrapped in a real `<xref>`. This is a candidate list to eyeball, not a claim
  that these are missed citations — deliberately conservative, since the same kind of
  pattern-matching that missed "M.H. Crawford" earlier would be far riskier applied to
  free-running body text. Only fires inside captions, never in `<body><p>` text.

**Deliberately does NOT do:**
- Generate mixed-citation prose
- Pick a language, translate place names, or decide punctuation style
- Touch DOIs (confirmed unnecessary — they already export correctly)
- Insert or fix the old year/pagination regex bugs (confirmed dead — current exports use
  proper `<month>` elements instead of the malformed `<year>` string that bug targeted)
- Harvest or parse the pinpoint/locator text (page, folio, note number) that follows a
  citation - it's read only for the verification comparison above, never extracted or stored
  (see §6, this is the next planned feature, not built yet)
- Restructure manuscript content (shelfmark splitting out of the title, archive fields, etc.)
  - manuscripts are only detected, moved, labeled, and sorted; everything else about their
    content is untouched

**Report sections, in the order they appear in `article_report.md`:**
1. Duplicate ref ids — likely content loss, highest severity
2. Dangling xrefs — needs a real `<ref>` created, not a label fix
3. Possible uncited references in captions — candidates only, verify by eye
4. Case-insensitive key matches — routine, informational, no action needed
5. Fixed automatically — done, just review if curious
6. Xref/author-text agreement — informational confirmations, nothing to do
7. Flagged for human review — actual decisions needed (mismatches, collisions, unverified
   label formats, page conflicts)
8. Verify xref targets — every authored manuscript, standing structural risk
9. No matching CSL-JSON record found
10. Errors

## 5. How to try it and report back

1. Run it against the real article.
2. Open `article_report.md` first — that's the fast way to see what happened without
   reading the whole diff.
3. For anything in "Flagged for human review" or "Verify xref targets" — check a few by eye
   against the actual article text. You don't need to check all of them, just enough to
   tell me whether the flags feel right, too aggressive, or are missing something.
4. If something looks *wrong* rather than just flagged — paste me the specific `<ref>` block
   (before) and the corresponding CSL-JSON record, the same way you did tonight. That's what
   let us catch every real bug so far; a description without the actual data is much harder
   to diagnose than the data itself.
5. If a whole category of ref behaves unexpectedly (e.g. every journal article in the file
   got mishandled the same way), say so as a pattern rather than listing each one — that's
   usually one fix, not many.

The fastest way to get something fixed is to paste the actual `<ref>` block and the
corresponding CSL-JSON record, not a description of the symptom. Every fix in this tool's
history came from a real example, not from anticipating a case in the abstract — a
constructed test case reliably misses whatever a real one catches.

## 6. Known limitations as of tonight (v2, unreleased/untagged)

- The 3-editor label format (`"A, B e C"`) is a guess — never confirmed against a real
  no-author, 3-editor, no-title-short case.
- The `>3`-author "et al." label format is confirmed only for one real case (AGD).
- The verification-window cutoff (splitting text at the next `;`) is a blunt heuristic — it
  works on everything tested tonight but hasn't been stress-tested broadly. Known to miss
  cases where an abbreviation contains a period right after the xref (this is why `;` was
  chosen over `.`, but it's still a heuristic, not a real sentence boundary detector).
- No locator/pinpoint harvesting yet — the trailing author text is verified against but not
  yet collected into the enrichment sidecar for reuse in the mixed-citation step. Deliberately
  scoped as harvest-only (capture verbatim) rather than parse-and-classify, since the shape of
  a pinpoint varies too much (page number vs. folio range vs. catalogue entry number) to guess
  safely - not built yet.
- Manuscript content itself (shelfmark extraction from the title, archive/call-number
  splitting) is still manual - the script only moves, labels, and sorts manuscript refs.
- Reporting language is Italian-oriented in a few flag messages even though the underlying
  logic is language-neutral.
- The sort function assumes `<ref>` is a direct child of `<ref-list>` with no intervening
  wrapper elements - untested against a ref-list with a different internal structure.

Expect a v2.x with each real run — every fix so far came from a real example breaking an
assumption (case-sensitivity in citation keys, duplicate years in title-short, dangling
xrefs, institutional curators with no title-short), not from anticipating it in advance.

## 7. Relationship to the retired BibTeX-based pipeline

An earlier iteration of this same problem (`add_all.py`, `add_all_no_doi_uri.py`, `clean.py`,
`finalxml.py`, `refactor.py` (v1), and a standalone `refactor.xslt`) was built incrementally
against a BibTeX-based pipeline and Sciflow's older JATS 1.3 export, rather than Better CSL
JSON and the current JATS 1.4 export. Sciflow no longer produces JATS 1.3 at all, so it isn't
just superseded by choice — it targets an export format that no longer exists. It was retired
and removed from the repo on this branch (recoverable from git history if ever needed) once
confirmed fully superseded by `refactor_v2.py` (built and tested against the current JATS 1.4
export), which:

- reads Better CSL JSON instead of BibTeX (structured arrays instead of fragile
  string-splitting on author names)
- rebuilds real author-year/title-short labels instead of reusing whatever citation-order
  text happened to already be in the body
- adds dangling-xref detection, label-collision detection, and case-insensitive key matching,
  none of which existed in the earlier version
- treats risky fixes (page mismatches, xref-target verification) as flag-only rather than
  silently overwriting

One behavioral difference to note if you ever dig up the old XSLT for comparison: it sorted
refs by citation order in the body, while `refactor_v2.py` sorts alphabetically by label —
an intentional change, not a regression.

## Status

Actively evolving. Expect a new patch version after essentially every real article run —
this is a "fix as we find it" tool, not a finished one.
