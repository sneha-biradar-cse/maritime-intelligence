"""
Parses NMPA's "Daily Vessel Position" PDFs (see
backend/app/services/vessel_position_archive.py, which downloads
them) into structured records.

The whole page is one pdfplumber table with a consistent 14-column
grid, but the *meaning* of those 14 columns changes between sections
-- "Berthed vessels" has date-of-arrival/date-of-berthing columns
that "Vessels Expected" doesn't, "Vessels Expected" has a DFT
(draft) column the others don't, etc. So this parser is a small
state machine: it walks the rows, recognises section-header rows
(a row where the first cell is one of a known label, everything
else blank) and switches which column map applies for the rows that
follow, until the next section header.

The free-text "Post Operation Meeting Changes" / "Movements" block
at the end is not tabular (it's a numbered list of sentences that
pdfplumber flattens into one cell) and is parsed separately with
regexes for the known sentence shapes ("X BERTHS AT B.NO.N AT
HH:MM HRS.", "X SAILS AT HH:MM HRS.", "X SHIFTS TO B.NO.N AT HH:MM
HRS.", "X RE-BERTHED AT B.NO.N AT HH:MM HRS.").

Coverage caveat (be honest about this, don't overclaim): this was
built and validated against one sample day (15-09-2026) plus spot
checks (see validate_sample() / __main__). NMPA's report layout may
have drifted across the year the archive covers (different software
version, an extra/missing section some days). Any date where the
parser's assumptions don't hold shows up as a row that doesn't match
a known section header and gets dropped into `unparsed_rows` in the
result, rather than silently mis-mapped into the wrong columns --
check that list before trusting a given day's output.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber

ARCHIVE_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position"
PARSED_DIR = Path(__file__).resolve().parents[3] / "data" / "daily_vessel_position_parsed"

# --------------------------------------------------------------
# Column maps: 14 grid columns -> field name, per section.
# `None` marks a column that's blank/unused in that section.
# --------------------------------------------------------------

BERTHED_COLUMNS = [
    "berth_no", "vessel_name", "run", "loa", "arrival_date",
    "berthing_date", "cargo", "agent", "receiver_shipper",
    "qty_day", "qty_total", "qty_balance", "etd", "stevedore",
]

ANCHORAGE_COLUMNS = [
    "sl_no", "vessel_name", "run", "loa", "doa", "clock_time",
    "waiting_duration", "cargo", "agent", "receiver_shipper",
    "qty", "reason_or_note", None, "stevedore",
]

# Same 14-column shape as the anchorage table; used for both
# "Tankers Scheduled for Berth No.12" and "...No.13" sections.
TANKERS_SCHEDULED_COLUMNS = ANCHORAGE_COLUMNS

EXPECTED_COLUMNS = [
    "sl_no", "vessel_name", "run", "draft", "loa", "eta_date",
    "eta_time", "cargo", None, "agent", "receiver_shipper",
    "qty", "berth_prefer", "stevedore",
]

# Section-header row text (col 0, case-normalised) -> (section key, column map)
# Includes "exptected", a confirmed typo in NMPA's own report used
# consistently across several dates in September 2025 -- without this
# alias, those days' "Vessels Expected" rows would silently be parsed
# under whatever the *previous* section's column map was instead
# (wrong field names, not just a missing section).
SECTION_HEADERS: dict[str, tuple[str, list]] = {
    "vessels waiting at anchorage": ("anchorage", ANCHORAGE_COLUMNS),
    "vessels expected": ("expected", EXPECTED_COLUMNS),
    "vessels exptected": ("expected", EXPECTED_COLUMNS),
}
# "tankers scheduled for berth no.NN" is matched by regex, not this dict.
TANKERS_HEADER_RE = re.compile(r"tankers scheduled for berth no\.?\s*(\d+)", re.I)

# The very first table header row starts the "berthed" section.
BERTHED_HEADER_FIRST_CELL = "b.no."

# The free-text block always starts with this literal marker,
# embedded inside a merged cell alongside "MOVEMENTS" further in.
NOTES_BLOCK_MARKER = "post operation meeting changes"

# On some dates (earlier in the archive; the letterhead apparently
# moved outside the table's bounding box at some point) the report's
# letterhead -- GSTIN/PAN/title/"DATE :DD-MM-YYYY" -- is itself the
# first row of the extracted table instead of separate page text.
# It's benign, not a structural surprise, so recognise and skip it
# rather than letting it inflate unparsed_rows on every such day.
LETTERHEAD_RE = re.compile(r"new mangalore port authority", re.I)

TIME_RE = r"\d{2}:\d{2}"
VESSEL_RE = r"[A-Z0-9 .()/'\-]+?"
# NMPA's own report mixes tense within the same document (e.g. "SAILS
# AT" for one vessel, "SAILED AT" for another) -- match both.
EVENT_PATTERNS = [
    ("re_berthed", re.compile(
        rf"(?P<vessel>{VESSEL_RE})\s+RE-BERTHED AT B\.?NO\.?\s*(?P<berth>\S+)\s+AT\s+(?P<time>{TIME_RE})\s*HRS\.?"
        rf"(?P<note>\([^)]*\))?", re.I)),
    ("berths", re.compile(
        rf"(?P<vessel>{VESSEL_RE})\s+BERTH(?:S|ED)? AT B\.?NO\.?\s*(?P<berth>\S+)\s+AT\s+(?P<time>{TIME_RE})\s*HRS\.?"
        rf"(?P<note>\([^)]*\))?", re.I)),
    ("shifts_to", re.compile(
        rf"(?P<vessel>{VESSEL_RE})\s+SHIFT(?:S|ED)? TO B\.?NO\.?\s*(?P<berth>\S+)\s+AT\s+(?P<time>{TIME_RE})\s*HRS\.?"
        rf"(?P<note>\([^)]*\))?", re.I)),
    ("sails", re.compile(
        rf"(?P<vessel>{VESSEL_RE})\s+SAIL(?:S|ED) AT\s+(?P<time>{TIME_RE})\s*HRS\.?"
        rf"(?P<note>\([^)]*\))?", re.I)),
]
DATE_HEADER_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")
NOTE_FOOTER_RE = re.compile(r"^\s*note\s*:", re.I)


@dataclass
class ParsedDay:
    report_date: str  # ISO, from the filename
    berthed: list[dict] = field(default_factory=list)
    anchorage: list[dict] = field(default_factory=list)
    tankers_scheduled: list[dict] = field(default_factory=list)
    expected: list[dict] = field(default_factory=list)
    movements: list[dict] = field(default_factory=list)
    unparsed_rows: list[list] = field(default_factory=list)


def _row_to_record(row: list, columns: list) -> dict | None:
    values = {}
    for col, cell in zip(columns, row):
        if col is None:
            continue
        text = (cell or "").replace("\n", " ").strip()
        values[col] = text
    # A fully blank record (e.g. a stray empty grid row) isn't real data.
    if not any(v for v in values.values()):
        return None
    return values


def _is_section_header(row: list) -> bool:
    first = (row[0] or "").strip()
    rest_blank = all(not (c or "").strip() for c in row[1:])
    return bool(first) and rest_blank


def _extract_notes_text(page) -> str | None:
    """Pulls the Post-Operation-Changes/Movements paragraph from the
    page's plain text, not the table grid -- see the note where this
    is called from for why the table cell isn't trustworthy here."""

    text = page.extract_text() or ""
    lower = text.lower()
    start = lower.find(NOTES_BLOCK_MARKER)
    if start == -1:
        return None

    end_candidates = []
    tm = lower.find("traffic manager", start)
    if tm != -1:
        end_candidates.append(tm + len("traffic manager"))
    note_footer = re.search(r"\n\s*note\s*:", lower[start:])
    if note_footer:
        end_candidates.append(start + note_footer.start())

    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def _parse_notes_block(text: str, report_date_iso: str) -> list[dict]:
    """Pulls structured berthing/sailing/shift events out of the
    free-text Post-Operation-Changes + Movements blob."""

    events = []

    # Date-bounded segments -- events belong to whichever "DD-MM-YYYY"
    # header precedes them (Post Operation Meeting Changes often
    # reports on the *previous* day or two, not the report's own date).
    markers = [(m.start(), m.group(1)) for m in DATE_HEADER_RE.finditer(text)]
    if not markers:
        bounds = [(0, len(text), report_date_iso)]
    else:
        bounds = []
        for i, (pos, raw_date) in enumerate(markers):
            end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            try:
                iso = datetime.strptime(raw_date, "%d-%m-%Y").date().isoformat()
            except ValueError:
                iso = report_date_iso
            bounds.append((pos, end, iso))

    movements_pos = text.lower().find("movements")

    for start, end, date_iso in bounds:
        segment = text[start:end]
        section = (
            "movement" if movements_pos != -1 and start >= movements_pos
            else "post_operation_change"
        )

        # Every event sentence ends in "...HRS" (optionally followed by
        # a parenthetical note, with no space before it) -- slice on
        # that boundary so each sentence is matched in isolation.
        # Without this, a vessel name's lazy match can otherwise bleed
        # backward across a sentence boundary and swallow the tail of
        # the previous one (both use the same permissive character
        # set). re.split() would work too but throws away the matched
        # delimiter text -- and the parenthetical note we want to keep
        # lives inside that delimiter -- so slice on end-positions
        # instead. The trailing period after HRS is inconsistently
        # present in the source document itself (confirmed: some
        # event lines end "...HRS" with no period at all) so it must
        # be optional here, not assumed.
        sentence_ends = [
            m.end() for m in re.finditer(r"HRS\.?(?:\([^)]*\))?", segment)
        ]
        sentences, prev = [], 0
        for end_pos in sentence_ends:
            sentences.append(segment[prev:end_pos])
            prev = end_pos
        if prev < len(segment):
            sentences.append(segment[prev:])

        # Each event line in the source is itself a numbered list that
        # restarts every day (e.g. "6 RV SAMUDRA SHAUDHIKAMA BERTHED AT
        # B.NO.6 AT 07:30 HRS.", where "6" is the 6th event that day,
        # not part of the ship's name) glued directly onto the vessel
        # name with just a space -- confirmed against the raw PDF text.
        # VESSEL_RE's permissive character class (needed to allow
        # periods/slashes in real names like "RV.SAMUDRA" or
        # "C.G.VARAHA") can't tell that digit apart from a name, so
        # strip a leading list-number (and the date-header text that
        # precedes the first list item in each date segment) before
        # matching, rather than in the pattern itself.
        sentences = [
            re.sub(r"^\s*(?:\d{2}-\d{2}-\d{4}\s*)?\d+\s+", "", s)
            for s in sentences
        ]

        for sentence in sentences:
            # Each correctly-sliced sentence should hold exactly one
            # event, but don't bet on that: use finditer (not the
            # first search() hit) across every pattern, so an
            # undetected boundary merge loses nothing silently -- it's
            # far better to occasionally double-count than to drop an
            # event without any sign it happened.
            for kind, pattern in EVENT_PATTERNS:
                for m in pattern.finditer(sentence):
                    events.append({
                        "date": date_iso,
                        "section": section,
                        "event_type": kind,
                        "vessel_name": m.group("vessel").strip(" .-"),
                        "berth_no": m.groupdict().get("berth"),
                        "time": m.group("time"),
                        "note": (m.groupdict().get("note") or "").strip("() ") or None,
                    })

    return events


def parse_pdf(path: Path) -> ParsedDay:
    stamp = path.stem  # "DD-MM-YYYY"
    report_date_iso = datetime.strptime(stamp, "%d-%m-%Y").date().isoformat()
    result = ParsedDay(report_date=report_date_iso)

    with pdfplumber.open(path) as pdf:
        rows: list[list] = []
        notes_text = None
        for page in pdf.pages:
            tables = page.find_tables()
            if tables:
                rows.extend(tables[0].extract())
            if notes_text is None:
                notes_text = _extract_notes_text(page)

    if notes_text:
        result.movements = _parse_notes_block(notes_text, report_date_iso)

    current_section = None
    current_columns = None
    current_context: dict[str, Any] = {}

    i = 0
    while i < len(rows):
        row = rows[i]
        first_cell = (row[0] or "").strip()
        first_lower = first_cell.lower()
        # The notes blob and the trailing "NOTE :" footer line both put
        # their text in column 1, not column 0 (unlike every real
        # section header), so check the whole row before anything else.
        row_text_lower = " ".join((c or "") for c in row).lower()

        if LETTERHEAD_RE.search(row_text_lower):
            i += 1
            continue

        if first_lower == BERTHED_HEADER_FIRST_CELL:
            current_section, current_columns, current_context = "berthed", BERTHED_COLUMNS, {}
            i += 2  # this table has a 2-row header
            continue

        if NOTES_BLOCK_MARKER in row_text_lower:
            # Content already pulled from page.extract_text() above --
            # the table-grid extraction of this specific row has been
            # observed to silently drop the paragraph text on some
            # dates (no visible cell borders within a free-text
            # paragraph confuses pdfplumber's table detection), so it
            # isn't trustworthy as the primary source. Just skip it
            # here so it doesn't fall through to unparsed_rows.
            i += 1
            continue

        if NOTE_FOOTER_RE.match((row[1] or "").strip() if len(row) > 1 else ""):
            i += 1
            continue

        if (
            re.fullmatch(r"[\d\s]+", first_cell or "")
            and all(not (c or "").strip() for c in row[1:])
        ):
            # A grid row whose only content is digits, with every
            # other cell blank, carries no usable information either
            # way: it's either a bare/empty berth-number slot with no
            # vessel (informationally the same as a "----" empty-berth
            # row) or, on some dates, the notes paragraph's own list
            # numbering (e.g. "1\n1\n2\n1\n2\n3...") getting split into
            # its own table cell while the paragraph text lands outside
            # the table grid entirely -- recovered separately via the
            # page.extract_text() fallback above. Either way, nothing
            # is lost by skipping it here instead of flagging it as an
            # unparsed row.
            i += 1
            continue

        if _is_section_header(row):
            if first_lower in SECTION_HEADERS:
                current_section, current_columns = SECTION_HEADERS[first_lower]
                current_context = {}
                i += 1
                # anchorage/expected also have their own sub-header row
                if i < len(rows) and _is_section_header(rows[i]) is False:
                    header_like = (rows[i][0] or "").strip().lower() in (
                        "sl.no.", "sl. no.", "sl no"
                    )
                    if header_like:
                        i += 1
                continue

            m = TANKERS_HEADER_RE.match(first_cell)
            if m:
                current_section = "tankers_scheduled"
                current_columns = TANKERS_SCHEDULED_COLUMNS
                current_context = {"berth_no": m.group(1)}
                i += 1
                continue

            if first_lower.startswith(NOTES_BLOCK_MARKER):
                # The whole notes blob is (usually) inside column 1 of
                # this same row.
                blob = " ".join((c or "") for c in row[1:])
                result.movements = _parse_notes_block(blob, report_date_iso)
                i += 1
                continue

            # An unrecognised section header -- record for manual review
            # rather than guessing.
            result.unparsed_rows.append(row)
            i += 1
            continue

        if current_columns is None:
            # Rows before any recognised section header (shouldn't
            # normally happen -- flag it).
            if any((c or "").strip() for c in row):
                result.unparsed_rows.append(row)
            i += 1
            continue

        record = _row_to_record(row, current_columns)
        if record is not None:
            record.update(current_context)
            record["report_date"] = report_date_iso
            getattr(result, current_section).append(record)

        i += 1

    return result


def parse_all(limit: int | None = None) -> list[ParsedDay]:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(ARCHIVE_DIR.glob("*.pdf"))
    if limit:
        pdf_paths = pdf_paths[:limit]

    parsed = []
    for path in pdf_paths:
        try:
            day = parse_pdf(path)
        except Exception as exc:  # noqa: BLE001 -- record and keep going
            print(f"FAILED to parse {path.name}: {exc}")
            continue
        out_path = PARSED_DIR / f"{path.stem}.json"
        out_path.write_text(json.dumps(asdict(day), indent=2))
        parsed.append(day)

    return parsed


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    days = parse_all(limit=n)
    total_unparsed = sum(len(d.unparsed_rows) for d in days)
    print(f"Parsed {len(days)} reports -> {PARSED_DIR}")
    print(f"Total unparsed rows across all days: {total_unparsed}")
    if days:
        d = days[-1]
        print(
            f"\nSample ({d.report_date}): "
            f"{len(d.berthed)} berthed, {len(d.anchorage)} anchorage, "
            f"{len(d.tankers_scheduled)} tankers-scheduled, "
            f"{len(d.expected)} expected, {len(d.movements)} movements"
        )
