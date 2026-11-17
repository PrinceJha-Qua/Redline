"""What reporter series exist, and when they were published.

Source: reporters-db (Free Law Project), the reporter database eyecite is built on. Two facts from it
prove a citation cannot exist without holding any case data:

* the series was never published: the North Eastern Reporter has N.E., N.E.2d and N.E.3d, so
  "982 N.E.4th 701" cannot exist;
* the series was not in print that year: F.3d began in 1993, so "475 F.3d 972 (8th Cir. 1983)"
  cannot exist.
"""
import re
from functools import lru_cache

import reporters_db

SLACK_YEARS = 1  # series overlap at their edges; never call a citation fake on a boundary year


def _norm(s):
    return re.sub(r"[\s.]", "", s).lower()


def _ordinal(edition, base):
    tail = _norm(edition)[len(_norm(base)):]
    m = re.match(r"(\d+)(?:d|th|st|nd|rd)$", tail)
    return int(m.group(1)) if m else (1 if not tail else None)


@lru_cache(maxsize=1)
def _index():
    """base reporter (normalized) -> {name, editions: {normalized edition: (name, start, end)}}"""
    out = {}
    for key, entries in reporters_db.REPORTERS.items():
        for e in entries:
            base = _norm(key)
            slot = out.setdefault(base, {"name": e.get("name", key), "abbr": key, "editions": {}})
            for ed, dates in e["editions"].items():
                slot["editions"][_norm(ed)] = (ed, dates.get("start"), dates.get("end"))
    return out


@lru_cache(maxsize=1)
def _editions():
    """normalized edition -> (name, start, end), including spelling variations"""
    out = {}
    for base in _index().values():
        out.update(base["editions"])
    for key, entries in reporters_db.REPORTERS.items():
        for e in entries:
            for variant, ed in (e.get("variations") or {}).items():
                if _norm(ed) in out:
                    out.setdefault(_norm(variant), out[_norm(ed)])
    return out


def series_dates(reporter):
    """(first year, last year or None) for a known series, else None."""
    hit = _editions().get(_norm(reporter))
    if not hit or not hit[1]:
        return None
    return hit[1].year, (hit[2].year if hit[2] else None)


def year_outside_series(reporter, year, earliest_known=None):
    """`earliest_known`: the earliest decision year Redline holds for this series. Cases decided before a
    series began can still be printed in it (F.3d starts in 1993 but holds cases decided in 1990)."""
    dates = series_dates(reporter)
    if not dates or not year:
        return None
    first, last = dates
    if earliest_known and earliest_known < first:
        if year < earliest_known - SLACK_YEARS:
            return (f"{reporter} began in {first}, and the earliest case printed in it was decided in "
                    f"{earliest_known}; a {year} {reporter} citation cannot exist.")
        first = earliest_known
    if year < first - SLACK_YEARS:
        return f"{reporter} began in {first}; a {year} {reporter} citation cannot exist."
    if last and year > last + SLACK_YEARS:
        return f"{reporter} ended in {last}; a {year} {reporter} citation cannot exist."
    return None


_PHANTOM = re.compile(r"\b(\d{1,4})\s+([A-Z][A-Za-z.' ]{0,24}?)\s?(\d{1,2})(d|th|st|nd|rd)\s+(?:at\s+)?(\d{1,5})\b")


def phantom_series(text, taken):
    """Citations to numbered series that were never published, e.g. "3 S.E.4th 887".

    `taken` holds spans eyecite already recognised; those are real series and are skipped.
    """
    found = []
    for m in _PHANTOM.finditer(text):
        start, end = m.span()
        if any(a < end and start < b for a, b in taken):
            continue
        base_raw, n = m.group(2).strip(), int(m.group(3))
        base = _index().get(_norm(base_raw))
        if not base:
            continue  # not a reporter we know; say nothing
        ordinals = [o for o in (_ordinal(name, base["abbr"]) for name, _, _ in base["editions"].values()) if o]
        if not ordinals or n <= max(ordinals):
            continue
        series = sorted((name for name, _, _ in base["editions"].values()), key=lambda s: _ordinal(s, base["abbr"]) or 0)
        found.append({"span": [start, end], "text": m.group(0), "volume": int(m.group(1)),
                      "reporter": f"{base_raw}{m.group(3)}{m.group(4)}", "page": int(m.group(5)),
                      "phantom": f"There is no {base_raw}{m.group(3)}{m.group(4)}: the {base['name']} was published as "
                                 f"{', '.join(series[:-1])} and {series[-1]}." if len(series) > 1 else
                                 f"There is no {base_raw}{m.group(3)}{m.group(4)}: the {base['name']} has one series, {series[0]}."})
    return found
