"""
refactor_v2.py
Consolidates rules A-J agreed during the Parigi RDF/JSON review session.

Input:
  - Sciflow JATS export (element-citation + optional untagged mixed-citation)
  - Better CSL JSON export from Zotero (NOT plain CSL JSON, NOT BibTeX)

Output (all written next to the input XML):
  - <name>_fixed.xml            corrected main ref-list + body
  - <name>_manuscripts.xml      refs split out as manuscript candidates (rule B, conservative)
  - <name>_enrichment.json      per-ref note/genre/event-*/abstract/collection-* carried
                                forward for the later mixed-citation conversion step (rule H)
  - <name>_report.md            everything flagged for human review (rules E, G, J, and any
                                 ref with no matching JSON record)

Explicit non-goals (by design, agreed tonight):
  - Does not generate mixed-citation prose.
  - Does not pick a language or translate place names.
  - Does not touch mixed-citation text content at all except reading it for verification.

Sorting: both the main ref-list and the split-out manuscripts list are sorted alphabetically
by <label> (diacritic- and case-insensitive), per house rule. Leading articles (L', Il, La...)
are NOT stripped for alphabetization - sorts literally as the label is written. If an article
shouldn't count, edit the title-short in Zotero, not the sort logic.
"""

import json
import unicodedata
import re
import sys
from lxml import etree

XLINK_NS = "http://www.w3.org/1999/xlink"


# ---------- CSL JSON helpers ----------

def load_csl_json(path):
    with open(path, encoding="utf-8") as f:
        records = json.load(f)
    by_id = {}
    by_id_lower = {}
    for rec in records:
        key = rec.get("id") or rec.get("citation-key")
        if key:
            by_id[key] = rec
            by_id_lower.setdefault(key.lower(), rec)  # first-wins if two keys collide only by case
    return by_id, by_id_lower


def lookup_record(ref_id, by_id, by_id_lower, report):
    """Exact match first. If that fails, try case-insensitive. This is expected to fire
    routinely whenever a citation key contains capital roman numerals (e.g. 'documentiIII1880')
    - Sciflow lowercases everything in the ref/@id it generates, while BetterBibTeX preserves
    the case as typed. This is a known, deterministic pattern, not a case-by-case judgment
    call, so it's logged separately from 'flags' rather than mixed in with things that
    actually need review."""
    rec = by_id.get(ref_id)
    if rec is not None:
        return rec
    rec = by_id_lower.get(ref_id.lower())
    if rec is not None:
        real_key = rec.get("id") or rec.get("citation-key")
        report["case_fallback"].append(f"{ref_id} <- {real_key} (case differs, likely roman numeral casing)")
    return rec


def extract_year(issued):
    if not issued:
        return None
    if "literal" in issued:
        return issued["literal"]
    if "date-parts" in issued and issued["date-parts"]:
        parts = issued["date-parts"]
        start = parts[0][0] if parts[0] else None
        if len(parts) > 1 and parts[1]:
            end = parts[1][0]
            if end and str(end) != str(start):
                return f"{start}-{end}"
        return str(start) if start else None
    return None


def surnames_of(people):
    out = []
    for p in people or []:
        if "literal" in p:
            out.append(p["literal"])
        else:
            out.append(p.get("family", "").strip())
    return [s for s in out if s]


def build_label(json_rec, xml_authors_fallback=None, xml_year_fallback=None):
    """Rule C. Author + year when a real author exists. When there's no author but
    title-short is set, that signals 'cite by title' (exhibition catalogues, corpora
    like AGD/DBI/EAA/LIMC) - use title-short + year, NOT the editor's surname.
    Editor-based naming is the fallback only when title-short is absent (e.g. Volpi 1994,
    a conventionally editor-cited scholarly volume with no title-short set)."""
    if json_rec and json_rec.get("type") == "manuscript":
        return json_rec.get("title-short") or json_rec.get("title", "")[:40]

    people = json_rec.get("author") if json_rec else None
    if not people and json_rec and json_rec.get("title-short") and json_rec.get("editor"):
        base = json_rec["title-short"]
        year = extract_year(json_rec.get("issued"))
        if year and str(year) in base:
            return base  # title-short already carries the year (e.g. "Documenti Inediti 1880, III")
        return f"{base} {year}".strip() if year else base

    if not people:
        people = json_rec.get("editor") if json_rec else None
    surnames = surnames_of(people) if people else (xml_authors_fallback or [])

    if len(surnames) == 1:
        base = surnames[0]
    elif len(surnames) == 2:
        base = f"{surnames[0]} / {surnames[1]}"
    elif len(surnames) == 3:
        base = f"{surnames[0]}, {surnames[1]} e {surnames[2]}"  # unverified for LABEL use specifically - flag
    elif len(surnames) > 3:
        base = f"{surnames[0]} et al."
    else:
        base = (json_rec.get("title-short") if json_rec else None) or ""

    year = extract_year(json_rec.get("issued")) if json_rec else xml_year_fallback
    if base:
        return f"{base} {year}".strip() if year else base

    # Nothing to build a base from at all (no author, no editor, no title-short) - this is
    # the collapse-to-bare-year failure mode. If a volume number exists, use it to avoid an
    # otherwise guaranteed collision with sibling volumes sharing the same year.
    volume = json_rec.get("volume") if json_rec else None
    if volume and year:
        return f"[untitled] vol. {volume}, {year}"
    if year:
        return f"[untitled] {year}"
    return "[untitled]"


# ---------- XML helpers ----------

def get_text(el, tag):
    node = el.find(tag)
    return node.text.strip() if node is not None and node.text else None


def person_group_from_json(people, role):
    """Builds a <person-group> element from CSL-JSON author/editor array.
    Uses <collab> for literal/institutional names per protocol doc."""
    if not people:
        return None
    pg = etree.Element("person-group", attrib={"person-group-type": role})
    for p in people:
        if "literal" in p:
            etree.SubElement(pg, "collab").text = p["literal"]
        else:
            name = etree.SubElement(pg, "name")
            etree.SubElement(name, "surname").text = p.get("family", "")
            if p.get("given"):
                etree.SubElement(name, "given-names").text = p["given"]
    return pg


def has_person_group(element_citation, role):
    return element_citation.find(f'.//person-group[@person-group-type="{role}"]') is not None


def looks_like_manuscript(json_rec, xml_pubtype):
    if not json_rec:
        return False
    if json_rec.get("type") == "manuscript":
        return True
    if xml_pubtype == "preprint" and (json_rec.get("archive") or json_rec.get("archive_location")):
        return True
    return False


# ---------- Main per-ref processing ----------

def process_ref(ref, by_id, by_id_lower, report):
    ref_id = ref.get("id")
    ec = ref.find("element-citation")
    if ec is None:
        report["errors"].append(f"{ref_id}: no <element-citation> found, skipped.")
        return None

    json_rec = lookup_record(ref_id, by_id, by_id_lower, report)
    if json_rec is None:
        report["no_match"].append(ref_id)

    old_label_node = ref.find("label")
    old_label_text = old_label_node.text if old_label_node is not None else None

    # --- fallback data straight from XML, used only if JSON record is missing ---
    xml_author_surnames = [
        n.findtext("surname") for n in ec.findall('.//person-group[@person-group-type="author"]/name')
        if n.findtext("surname")
    ]
    xml_year = get_text(ec, "year")

    # --- Rule B: manuscript detection (conservative, structural signal only) ---
    xml_pubtype = ec.get("publication-type")
    is_manuscript = looks_like_manuscript(json_rec, xml_pubtype)

    # --- Rule C: label replace (not create) ---
    new_label = build_label(json_rec, xml_author_surnames, xml_year)
    if old_label_node is None:
        old_label_node = etree.SubElement(ref, "label")
        ref.insert(0, old_label_node)
    old_label_node.text = new_label

    if json_rec and len(surnames_of(json_rec.get("author") or json_rec.get("editor") or [])) > 2:
        report["flags"].append(f"{ref_id}: label uses unverified >2-author 'et al.' pattern - confirm wording.")

    # --- Rule A: article-title reclassification by JSON type (not XML attribute) ---
    art_title = ec.find("article-title")
    if art_title is not None and json_rec:
        jtype = json_rec.get("type")
        if jtype in ("book", "thesis", "motion_picture") or is_manuscript:
            art_title.tag = "source"
        elif jtype in ("chapter", "paper-conference", "webpage", "entry-dictionary"):
            art_title.tag = "part-title"
            container = json_rec.get("container-title")
            if container and ec.find("source") is None:
                src = etree.Element("source")
                src.text = container
                art_title.addnext(src)
        elif jtype == "article-journal":
            pass  # correct as-is
        else:
            report["flags"].append(f"{ref_id}: unhandled CSL type '{jtype}' for article-title - left as-is, check manually.")
    elif art_title is not None and not json_rec:
        report["flags"].append(f"{ref_id}: article-title present but no JSON record to confirm reclassification - left as-is.")

    # --- Rule F: inject missing editors/authors from JSON ---
    if json_rec:
        for role in ("author", "editor"):
            people = json_rec.get(role)
            if people and not has_person_group(ec, role):
                pg = person_group_from_json(people, role)
                if pg is not None:
                    anchor = ec.find("source")
                    if anchor is None:
                        anchor = ec.find("article-title")
                    if anchor is None:
                        anchor = ec.find("part-title")
                    if anchor is not None:
                        anchor.addprevious(pg)
                    else:
                        ec.insert(0, pg)
                    report["fixed"].append(f"{ref_id}: injected missing {role} person-group from JSON.")

    # --- Rule E: fpage/lpage cross-check, flag only, never silently overwrite ---
    if json_rec and json_rec.get("page"):
        json_page = json_rec["page"]
        fpage, lpage = get_text(ec, "fpage"), get_text(ec, "lpage")
        if fpage is None and lpage is None:
            parts = re.split(r"[-\u2013]", json_page, maxsplit=1)
            fp = etree.SubElement(ec, "fpage")
            fp.text = parts[0].strip()
            if len(parts) == 2:
                lp = etree.SubElement(ec, "lpage")
                lp.text = parts[1].strip()
            report["fixed"].append(f"{ref_id}: inserted missing fpage/lpage from JSON page='{json_page}'.")
        else:
            existing = f"{fpage}" + (f"-{lpage}" if lpage else "")
            if existing.replace(" ", "") != json_page.replace(" ", "").replace("\u2013", "-"):
                report["flags"].append(
                    f"{ref_id}: PAGE MISMATCH - XML has '{existing}', JSON has '{json_page}'. Needs human decision (do not auto-resolve)."
                )

    # --- Rule G: publisher-loc possibly bled from event-place ---
    if json_rec:
        xml_loc = get_text(ec, "publisher-loc")
        json_place = json_rec.get("publisher-place")
        event_place = json_rec.get("event-place")
        if xml_loc and event_place and xml_loc == event_place and json_place and json_place != event_place:
            loc_node = ec.find("publisher-loc")
            loc_node.text = json_place
            report["fixed"].append(
                f"{ref_id}: publisher-loc '{event_place}' matched event-place, replaced with JSON publisher-place '{json_place}'."
            )
        elif not xml_loc and json_place:
            pub_name = ec.find("publisher-name")
            loc = etree.Element("publisher-loc")
            loc.text = json_place
            if pub_name is not None:
                pub_name.addnext(loc)
            else:
                ec.append(loc)
            report["fixed"].append(f"{ref_id}: inserted missing publisher-loc '{json_place}' from JSON.")

    # --- Rule H: carry forward fields Sciflow drops entirely, for the later mixed-citation step ---
    if json_rec:
        enrichment = {}
        for key in ("note", "genre", "event-place", "event-date", "event-title",
                    "abstract", "collection-title", "collection-number", "archive",
                    "archive_location"):
            if json_rec.get(key):
                enrichment[key] = json_rec[key]
        if enrichment:
            report["enrichment"][ref_id] = enrichment

    # --- Rule J: flag generic/collision-prone old labels for manual xref-target verification.
    # Any manuscript with a named author is inherently collision-prone under an author-date
    # label - two different shelfmarks by the same author in the same (or absent) year would
    # produce identical labels - so this is flagged regardless of whether the specific old
    # label happened to literally say "s.d."/"n.d.".
    generic_undated = old_label_text and re.search(r"\bs\.?d\.?\b|\bn\.?d\.?\b", old_label_text, re.IGNORECASE)
    manuscript_with_author = is_manuscript and json_rec and json_rec.get("author")
    if generic_undated or manuscript_with_author:
        reason = "generic/undated label" if generic_undated else "authored manuscript (collision-prone under author-date labelling regardless of this instance's date)"
        report["verify_xref_targets"].append(
            f"{ref_id}: {reason} - verify every <xref rid=\"{ref_id}\"> in the body actually "
            f"corresponds to THIS ref's content (shelfmark {json_rec.get('title-short') if json_rec else '?'}), "
            f"not a sibling item by the same author."
        )

    return {"old_label": old_label_text, "new_label": new_label, "is_manuscript": is_manuscript}


# ---------- Body xref propagation (Rule I) + duplicate-text flagging (Rule D) ----------

def sort_key(label):
    """Diacritic-insensitive, case-insensitive sort key. Deliberately does NOT strip
    leading articles (L', Il, La, etc.) - literal sort as the label is actually written.
    If an article shouldn't count for alphabetization, that's a title-short edit in Zotero,
    not a sorting rule here."""
    normalized = unicodedata.normalize("NFKD", label or "")
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    return stripped.lower()


def sort_ref_list_by_label(ref_list_el, report, list_name="ref-list"):
    """Sorts <ref> elements by label. Any <!-- comment --> immediately preceding a <ref>
    (e.g. the duplicate-id markers) travels WITH that ref during reordering - a plain
    findall("ref")-based remove/append would strand comments at their original position
    while the actual refs moved elsewhere, exactly the bug that surfaced when duplicate-id
    markers ended up all bunched at the top of the list instead of by their respective refs."""
    children = list(ref_list_el)
    groups = []
    pending_comments = []
    for child in children:
        if child.tag is etree.Comment:
            pending_comments.append(child)
        elif child.tag == "ref":
            groups.append((pending_comments, child))
            pending_comments = []
        else:
            pending_comments.append(child)  # unexpected sibling type, keep attached conservatively
    trailing = pending_comments  # comments with no following ref (rare) - kept at the end, in place

    missing = [ref.get("id") for _, ref in groups
               if ref.find("label") is None or not (ref.find("label").text or "").strip()]
    if missing:
        report["flags"].append(
            f"{list_name}: cannot sort - these refs have no label text: {missing}. Fix labels first."
        )
        return

    groups_sorted = sorted(groups, key=lambda pair: sort_key(pair[1].find("label").text))

    for child in children:
        ref_list_el.remove(child)
    for comments, ref in groups_sorted:
        for c in comments:
            ref_list_el.append(c)
        ref_list_el.append(ref)
    for c in trailing:
        ref_list_el.append(c)


AUTHOR_YEAR_PATTERN = re.compile(
    r"\b([A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'\u2019-]+(?:\s*/\s*[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'\u2019-]+)?)"
    r"\s*,?\s*(1[5-9]\d{2}|20\d{2})\b"
)


def _collect_text_excluding_xref_content(el):
    """Concatenates text of an element and its descendants, EXCLUDING text that sits inside
    an <xref> (that's a real, already-tracked citation) but INCLUDING an xref's .tail (text
    that follows it - same distinction used elsewhere for the verification comparison)."""
    parts = [el.text or ""]
    for child in el:
        if child.tag != "xref":
            parts.append(_collect_text_excluding_xref_content(child))
        parts.append(child.tail or "")
    return "".join(parts)


def find_possible_uncited_references(root, report):
    """Scoped, conservative scan: only inside <fig>/<table-wrap> (captions live there), only
    text not already wrapped in a real <xref>, only a loose author-year shape. This is a
    candidate list for a human to eyeball, NOT a claim that these are missed citations - the
    same kind of pattern-match that broke on 'M.H. Crawford' elsewhere in this tool would be
    far riskier applied to free-running body text, so this deliberately stays narrow."""
    for container in root.findall(".//fig") + root.findall(".//table-wrap"):
        text = _collect_text_excluding_xref_content(container)
        for match in AUTHOR_YEAR_PATTERN.finditer(text):
            snippet_start = max(0, match.start() - 20)
            snippet = text[snippet_start: match.end() + 20].strip()
            report["possible_uncited"].append(
                f"<{container.tag}> contains plain-text pattern {match.group(0)!r} "
                f"(not inside an <xref>) - candidate for a missed citation, context: "
                f"'...{snippet}...'. Verify by eye - this is a loose pattern match, not a "
                f"confirmed citation."
            )


def find_duplicate_ref_ids(root, ref_list_el, report):
    """Detects two <ref> elements sharing the same @id within the ref-list itself.

    When element-citation content is identical across copies, there are two plausible causes
    with very different implications, and this cannot tell them apart on its own:

    1. CONTENT LOSS: two genuinely different Zotero records shared a citation-key stem and
       differed only by a disambiguating letter suffix (e.g. russo2012a/b); Sciflow stripped
       the suffix when generating ref/@id, both collapsed onto one id, and one record's real
       content was overwritten by the other's.
    2. BENIGN STALE DUPLICATE: the same single reference was cited twice in the body (e.g.
       twice in one footnote); Zotero once had a genuine duplicate item for it (hence the
       leftover a/b in the old mixed-citation text) that was later merged into one item, but
       Sciflow's ref-list generation accumulated a second, now-redundant <ref> across export
       cycles rather than fully rebuilding. In this case nothing is lost - one copy can simply
       be deleted.

    A strong signal for (2) over (1): if the body's <xref>s pointing at this id ALREADY show
    identical link text to each other (not two different original suffixes), the duplication
    likely predates any suffix-stripping and is the benign case. This function checks that
    signal and reports it, but does not decide for you - verify against Zotero either way
    before deleting anything, since a wrong guess here is exactly the kind of assumption that
    caused an earlier, wrongly-alarming version of this message."""
    seen = {}
    for ref in ref_list_el.findall("ref"):
        rid = ref.get("id")
        seen.setdefault(rid, []).append(ref)
    for rid, refs in seen.items():
        if len(refs) > 1:
            mixed_texts = [r.findtext("mixed-citation", "").strip() for r in refs]
            same_content = len({etree.tostring(r.find("element-citation")) for r in refs}) == 1
            body_xref_texts = {x.text for x in root.findall(f'.//xref[@rid="{rid}"]')}
            body_already_consistent = len(body_xref_texts) <= 1

            if same_content and body_already_consistent:
                diagnosis = (
                    "Body xrefs pointing at this id already agree with each other - this looks "
                    "like the BENIGN case (same reference cited twice, Zotero-side duplicate "
                    "resolved earlier, Sciflow left a stale extra <ref>). Likely safe to delete "
                    "one copy, but confirm against Zotero before doing so."
                )
            elif same_content:
                diagnosis = (
                    "Body xrefs disagree with each other even though ref-list content is "
                    "identical - this is more consistent with CONTENT LOSS from a stripped "
                    "citation-key suffix. Check Zotero for two records sharing this stem "
                    "before assuming either copy's content is correct."
                )
            else:
                diagnosis = "Content differs between copies - verify both against Zotero."

            report["duplicate_ref_ids"].append(
                f"id='{rid}' appears {len(refs)} times in the ref-list. "
                f"element-citation content {'is IDENTICAL' if same_content else 'DIFFERS'} across copies. "
                f"mixed-citation per copy: {mixed_texts}. {diagnosis}"
            )

            # Mark directly in the XML too - a comment immediately before each duplicate,
            # so it's findable while working in Oxygen without cross-referencing the report.
            for i, ref in enumerate(refs):
                comment = etree.Comment(
                    f" DUPLICATE REF ID {i + 1}/{len(refs)}: id='{rid}' - "
                    f"{'benign (body already consistent), likely safe to delete one copy' if (same_content and body_already_consistent) else 'CHECK CONTENT before deleting either copy'} "
                    f"- see article_report.md for full diagnosis "
                )
                ref.addprevious(comment)


def find_dangling_xrefs(root, ref_list_el, report):
    """A citation can exist in the body with no corresponding <ref> in the ref-list at all -
    e.g. the author cited something that was never added to the bibliography, and whoever
    added it to Zotero afterward filed it in a collection that isn't part of this article's
    export. This is a different failure mode from 'no matching JSON record' (which requires
    a <ref> to exist in the first place) and needs its own check."""
    existing_ids = {ref.get("id") for ref in ref_list_el.findall("ref")}
    seen = set()
    for xref in root.findall('.//xref[@ref-type="bibr"]'):
        rid = xref.get("rid")
        if rid and rid not in existing_ids and rid not in seen:
            seen.add(rid)
            report["dangling_xrefs"].append(
                f"rid='{rid}' (link text: {xref.text!r}) is cited in the body but has NO "
                f"<ref id=\"{rid}\"> in the ref-list at all. This was likely never added to "
                f"the bibliography, or was added to Zotero but filed outside this article's "
                f"export collection. Needs a real <ref> created, not just a label fix."
            )


def check_label_collisions(label_map, report):
    """Global pass: flag any two refs that ended up with the identical final label. This
    catches collapse-to-bare-year cases (e.g. two volumes of the same multi-volume set
    published in the same year, both missing editor and title-short) that no per-ref check
    would catch, since each ref looks individually 'fine' in isolation."""
    by_label = {}
    for rid, info in label_map.items():
        by_label.setdefault(info["new_label"], []).append(rid)
    for label, rids in by_label.items():
        if len(rids) > 1:
            report["flags"].append(
                f"LABEL COLLISION: {rids} all resolved to the identical label {label!r}. "
                f"These need to be manually disambiguated - check what data is actually "
                f"missing in Zotero for each (editor? title-short?) rather than just patching "
                f"the label text."
            )


def propagate_labels_and_flag_duplicates(root, label_map, by_id, by_id_lower, report):
    """Rule I + D/J (merged): xref text gets synced to the ref-list label (I), but the
    trailing author-written text after each xref is NEVER touched. That trailing text is
    the person's own verification anchor - it's what the author originally typed, kept
    deliberately to confirm the auto-generated xref->rid attachment is correct. This
    function only COMPARES and REPORTS agreement/disagreement; it never strips anything."""
    for xref in root.findall('.//xref[@ref-type="bibr"]'):
        rid = xref.get("rid")
        if rid not in label_map:
            continue
        new_label = label_map[rid]["new_label"]
        original_xref_text = xref.text or ""
        json_rec = by_id.get(rid) or by_id_lower.get(rid.lower())
        title_short = (json_rec.get("title-short") if json_rec else None) or ""

        xref.text = new_label  # rule I: keep the visible link text in sync with the ref-list label

        tail = xref.tail or ""
        next_sibling = xref.getnext()
        sib_text = ""
        if next_sibling is not None and next_sibling.tag in ("italic", "bold"):
            sib_text = (next_sibling.text or "").strip()

        candidate = tail if tail.strip() else sib_text
        if not candidate:
            continue  # nothing to verify against - not flagged, simply no anchor text exists here

        cutoff = re.search(r"[;]", candidate)  # ';' is a safer cutoff than '.' - avoids "M.H."-style breaks
        window = candidate[: cutoff.start()] if cutoff else candidate[:80]

        orig_norm = re.sub(r"[^\w]", "", original_xref_text).lower()
        title_short_norm = re.sub(r"[^\w]", "", title_short).lower()
        window_norm = re.sub(r"[^\w]", "", window).lower()
        surname_tokens = [t for t in re.split(r"[\s/]+", original_xref_text) if t]
        hits = [t for t in surname_tokens if t.lower() in window_norm]

        is_ms = json_rec.get("type") == "manuscript" if json_rec else False

        if is_ms and title_short_norm and title_short_norm in window_norm:
            report["verified_matches"].append(
                f"{rid}: manuscript shelfmark ({title_short!r}) found in surrounding text - "
                f"strong confirmation, rid attachment looks correct."
            )
        elif is_ms and orig_norm in window_norm and not title_short_norm:
            report["verified_matches"].append(
                f"{rid}: xref text matches, but this is an authored manuscript with no title-short "
                f"to cross-check against - author-date agreement alone is weak evidence here, since "
                f"other manuscripts by the same author could produce an identical match. Spot-check."
            )
        elif orig_norm and orig_norm in window_norm:
            report["verified_matches"].append(
                f"{rid}: xref text and author's original citation agree ({window.strip()!r}) - "
                f"rid attachment looks correct."
            )
        elif title_short_norm and title_short_norm in window_norm:
            report["verified_matches"].append(
                f"{rid}: author cited by title-short ({title_short!r}) rather than author-year - "
                f"agrees with the record, rid attachment looks correct."
            )
        elif hits:
            report["verified_matches"].append(
                f"{rid}: partial agreement ({window.strip()!r} contains {hits}) - likely correct, "
                f"spot-check recommended."
            )
        else:
            report["flags"].append(
                f"{rid}: NO AGREEMENT between xref text {original_xref_text!r} and the text immediately "
                f"following it ({window.strip()!r}). This may indicate the xref is attached to the WRONG "
                f"rid (cf. the Ligorio n.d. case) - verify by hand, do not assume either side is correct."
            )


# ---------- Manuscript split (conservative) ----------

def split_manuscripts(ref_list_el, ref_results):
    manuscripts_container = etree.Element("ref-list")
    for ref in list(ref_list_el.findall("ref")):
        rid = ref.get("id")
        if ref_results.get(rid, {}).get("is_manuscript"):
            ref_list_el.remove(ref)
            manuscripts_container.append(ref)
    return manuscripts_container


# ---------- Driver ----------

def main(xml_path, json_path):
    by_id, by_id_lower = load_csl_json(json_path)
    tree = etree.parse(xml_path)
    root = tree.getroot()
    ref_list_el = root.find(".//ref-list")

    report = {"fixed": [], "flags": [], "errors": [], "no_match": [],
              "enrichment": {}, "verify_xref_targets": [], "verified_matches": [],
              "dangling_xrefs": [], "case_fallback": [], "possible_uncited": [],
              "duplicate_ref_ids": []}

    label_map = {}
    ref_results = {}
    for ref in ref_list_el.findall("ref"):
        result = process_ref(ref, by_id, by_id_lower, report)
        if result:
            rid = ref.get("id")
            label_map[rid] = result
            ref_results[rid] = result

    find_dangling_xrefs(root, ref_list_el, report)
    find_possible_uncited_references(root, report)
    check_label_collisions(label_map, report)
    propagate_labels_and_flag_duplicates(root, label_map, by_id, by_id_lower, report)
    manuscripts_el = split_manuscripts(ref_list_el, ref_results)
    sort_ref_list_by_label(ref_list_el, report, "Bibliografia")
    if len(manuscripts_el):
        sort_ref_list_by_label(manuscripts_el, report, "Manoscritti")

    # Duplicate-id detection and comment-marking runs LAST, on each already-split,
    # already-sorted list separately - this avoids needing to carry marker comments through
    # split_manuscripts or the sort (both of which only move <ref> elements, not their
    # preceding siblings), by simply never inserting a comment before either operation runs.
    find_duplicate_ref_ids(root, ref_list_el, report)
    if len(manuscripts_el):
        find_duplicate_ref_ids(root, manuscripts_el, report)

    base = xml_path.rsplit(".", 1)[0]

    tree.write(f"{base}_fixed.xml", pretty_print=True, encoding="UTF-8", xml_declaration=True)

    if len(manuscripts_el):
        etree.ElementTree(manuscripts_el).write(
            f"{base}_manuscripts.xml", pretty_print=True, encoding="UTF-8", xml_declaration=True
        )

    with open(f"{base}_enrichment.json", "w", encoding="utf-8") as f:
        json.dump(report["enrichment"], f, ensure_ascii=False, indent=2)

    with open(f"{base}_report.md", "w", encoding="utf-8") as f:
        f.write("# refactor_v2 report\n\n")
        for section, title in [
            ("duplicate_ref_ids", "DUPLICATE REF IDS - severity depends on diagnosis below, check each"),
            ("dangling_xrefs", "DANGLING XREFS - cited but missing from ref-list entirely"),
            ("possible_uncited", "Possible uncited references in figure/table captions (unverified pattern match)"),
            ("case_fallback", "Case-insensitive key matches (routine - roman-numeral casing, no action needed)"),
            ("fixed", "Fixed automatically"),
            ("verified_matches", "Xref/author-text agreement (no changes made - informational)"),
            ("flags", "Flagged for human review (not auto-applied)"),
            ("verify_xref_targets", "Verify xref targets (generic old label)"),
            ("no_match", "No matching CSL-JSON record found"),
            ("errors", "Errors"),
        ]:
            f.write(f"## {title}\n\n")
            items = report[section]
            if not items:
                f.write("_none_\n\n")
                continue
            for item in items:
                f.write(f"- {item}\n")
            f.write("\n")

    print(f"Done. Wrote {base}_fixed.xml, _manuscripts.xml (if any), _enrichment.json, _report.md")


if __name__ == "__main__":
    xml_arg = sys.argv[1] if len(sys.argv) > 1 else input("XML path: ")
    json_arg = sys.argv[2] if len(sys.argv) > 2 else input("Better CSL JSON path: ")
    main(xml_arg, json_arg)
