# Data

Everything in Redline's stores is rebuilt from public sources with `make data` (core store) and
`make pack` (federal pack). Nothing is hand-edited.

## Sources

| Source | What Redline takes | Licence |
|---|---|---|
| [reporters-db](https://github.com/freelawproject/reporters-db), Free Law Project (ships with eyecite) | Which reporter series exist, to prove "982 N.E.4th 701" impossible | BSD |
| [Caselaw Access Project](https://static.case.law), Harvard Law School Library: *United States Reports* (vols. 1–572, 1754–2014) and *Federal Reporter, Third Series* (vols. 1–935, 1990–2019) | Every case's name, court, date and page range; parallel citations; the citations each opinion makes, already resolved to case ids; the court's parenthetical on a citation | Released without restriction (March 2024) |
| [Wikipedia: List of overruled United States Supreme Court decisions](https://en.wikipedia.org/wiki/List_of_overruled_United_States_Supreme_Court_decisions), which follows the Library of Congress table | 144 explicit overrulings, including 6 partial ones | CC BY-SA 4.0 |

Downloads land in `data/raw/` (about 2.4 GB, not committed). `ingest/fetch_cap.py` is resumable
and refuses truncated files.

## Coverage

| Reporter | Volumes | Years | Cases in the store | Complete |
|---|---|---|---|---|
| U.S. | 1–572 | 1754–2014 | 29,144 opinions of 300 words or more | yes: every page of every volume is mapped |
| F.3d | 1–935 | 1990–2019 | 141,484 | yes |

A page map lets Redline call a citation **fabricated**: when the page belongs to a different case,
or a different case starts on it, the citation cannot be right. Outside these reporters a citation is
**unverifiable**, never fabricated.

### Checking the page maps against the courts

The Harvard data is not perfect. Some volumes are missing cases, and a few have page numbers shifted
against the printed books. `bench/pagemap_audit.py` finds this from the data itself: every opinion
lists the citations it makes, including ones CAP could not link to a case. When two or more courts
cite a page as the start of a case and the data has no case starting there, the page map is wrong at
that point. 4,056 such pages exist; 1,895 fall inside another case.

The store builder uses the audit two ways:

- each volume records those pages (`cited_starts`); a citation to one is never called fabricated;
- a volume with 2 or more such pages inside other cases, or 10 or more in all, is marked
  `complete: false` and never used to prove a fabrication.

Trusted volumes: 844 of 935 in F.3d, 352 of 572 in U.S. Reports. Volume 925 F.3d, where
*Varghese* points, is trusted: courts cite every one of its cases where the data says they start.

Short U.S. Reports entries (under 300 words) are almost always one-line orders such as
"certiorari denied". They are not stored as cases, but their pages are recorded on the volume
(`order_pages`) so a citation to one is not mistaken for a fabrication.

Supreme Court decisions after volume 572 (2014) appear only when the overruling list names them,
for example *Dobbs* (597 U.S. 215) and *Loper Bright* (603 U.S. 369). They are stored with
`stub: true`: name and citation, no citations of their own.

## The two stores

| | Core store `data/redline-us/` | Federal pack `data/packs/redline-federal/` |
|---|---|---|
| Committed to git | yes | no; published as a release download |
| Supreme Court → Supreme Court citations | 294,209 | same |
| Appeals court → Supreme Court citations | 689,038 | same |
| Appeals court → appeals court citations | — | 1,195,937 |
| Total citations | 983,247 | 2,179,184 |
| Size on disk | 51.6 MB | 77.4 MB |
| Parentheticals | all of the above | all |

Both are Relate **directory stores**. The same graph written as a single `.rl` file measured
about eight times larger (a 8.6 MB directory store against a 73.8 MB `.rl` for the Supreme Court
alone), because a `.rl` file keeps the space its write log and earlier snapshots once used.
`relate clone data/redline-us data/redline-us.rl` produces a compact single file when one is
wanted.

## Graph

```
(:Reporter {abbr, name, first_vol, last_vol, volumes, first_year, last_year, complete})
  -[:HAS_VOLUME]->
(:Volume {key, reporter, vol, first_page, last_page, cases, order_pages, cited_starts, complete})
  -[:CONTAINS]->
(:Case {id, name, title?, cite, reporter, vol, first_page, last_page, date, year, court,
        authority, cited_by, status?, stub?})
  -[:DECIDED_BY]-> (:Court {id, name, level})

(:Case)-[:CITES {weight, parenthetical?}]->(:Case)
(:Case)-[:OVERRULES {partial, topic, source}]->(:Case)
(:Citation {text})-[:CITATION_OF]->(:Case)          parallel cites: "93 S.Ct. 705"
(:Meta {pack, built, cases, citations, overrulings, volumes, sources})
```

Case ids are `<reporter>:<volume>:<first page>`, such as `US:410:113` or `F3d:925:1291`. When two
opinions start on the same page, the longer one keeps the plain id and the others get `.2`, `.3`.

`authority` is the HITS authority score over the citation graph (Kleinberg 1999), the measure
Fowler and Jeon used for Supreme Court precedent. `cited_by` counts distinct citing cases.
`status` is `overruled` or `overruled in part` where the overruling list says so.

## Measured on the core store

Apple Silicon laptop, `python bench/scale.py`, 20 runs per row.

| Question | Cases returned | Median |
|---|---|---|
| Cases that cite *Chevron* (1 hop) | 5,082 | 0.8 ms |
| … or cite a case that does (2 hops) | 18,224 | 14 ms |
| … 3 hops | 58,574 | 86 ms |
| Appeals-court cases citing any overruled Supreme Court case | 12,096 | 16 ms |
| … through one intermediate case | 74,710 | 281 ms |

Build: about 2 minutes from the downloads. Store size: 51.6 MB (it holds each case's full caption,
so co-defendants and relators the short name drops can still be matched).

## Measured on the federal pack

Same machine and runs. The extra appeals-to-appeals citations widen every hop.

| Question | Cases returned | Median | Worst |
|---|---|---|---|
| Cases that cite *Chevron* (1 hop) | 5,082 | 0.8 ms | 2.3 ms |
| 2 hops | 33,225 | 33 ms | 38 ms |
| 3 hops | 99,006 | 255 ms | 283 ms |
| Appeals-court cases resting on an overruled Supreme Court case, through one intermediate case | 91,714 | 422 ms | |

Build: about 2 minutes from the downloads.
