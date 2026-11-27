# Declarations

What Redline uses, what it was built with, and when the work was done.

## Relate

| Feature | Where |
|---|---|
| Embedded engine, Python package `relate-db` | `redline/store.py`, `ingest/build_store.py` |
| Directory store (Parquet), committed to the repo | `data/redline-us/` |
| Read-only connections (the store's files are byte-identical after every test) | `redline/store.py`, `tests/test_store.py` |
| Cypher: `MATCH`, `OPTIONAL MATCH`, `UNWIND` bulk load, variable multi-hop paths, aggregation | `redline/verify.py`, `redline/status.py`, `redline/service.py` |
| Uniqueness constraints and a property index | `ingest/build_store.py` |
| Full-text index (`case_name`), queried with `db.index.fulltext.queryNodes` | `redline/service.py`, `redline/agent.py` |
| Full-text index on a relationship property (`cites_parenthetical` on `CITES`), queried with `db.index.fulltext.queryRelationships` | `redline/agent.py` (`find_authority`), `ingest/build_store.py` |
| Transactions on a read-only connection: writes staged, queried, refused at commit, rolled back | `redline/store.py` (`hypothetical`), `redline/agent.py` (`what_if`), `tests/test_agent.py` |
| One connection per thread, owned by a worker that serves the web app and the MCP server | `redline/store.py` |

## Third-party code and data

| Name | Use | Licence |
|---|---|---|
| eyecite, reporters-db (Free Law Project) | Finding citations in text; the list of real reporter series | BSD |
| FastAPI, Uvicorn | Web app and HTTP API | MIT / BSD |
| MCP Python SDK | MCP server (stdio and HTTP) | MIT |
| pytest, httpx | Tests | MIT / BSD |
| pyarrow (optional, `.[audit]`) | `bench/crosscheck.py` reads the store's Parquet files without Relate | Apache 2.0 |
| Docker, `python:3.12-slim` | The hosted demo (`Dockerfile`) | Apache 2.0 / PSF |
| AI Hallucination Cases database, Damien Charlotin | Citations courts found fabricated (`bench/wild.py`, `/replay`) | CC BY 4.0 |
| Caselaw Access Project, Harvard Law School Library | Every case, page range and citation in the store | Released without restriction |
| Wikipedia, *List of overruled United States Supreme Court decisions* | The 144 overrulings | CC BY-SA 4.0 |
| Fowler & Jeon, *The Authority of Supreme Court Precedent* (2008) | Method only: HITS authority scores, implemented in `ingest/build_store.py` | — |
| LePhantomCite (Princeton, 2026) | Benchmark data, downloaded by `make bench`, not redistributed | See the dataset |

No code was copied from other hackathon entries. Some ideas were, and are credited here:

| Idea | From | In Redline |
|---|---|---|
| Agent experiment arms: plain / "be careful" warning / tool | [Precedent](https://github.com/ZNLong2203/precedent) | `bench/agent_experiment.py` |
| A what-if inside a transaction that is rolled back | Precedent, [Blind Flange](https://github.com/loksai-codes/blind-flange) | `what_if_overruled` |
| A suggested fix with each finding | Precedent (`fix-status`), [memory-pr](https://github.com/himanshu748/memory-pr) (one-click fixes) | repairs for fabricated citations |
| Time travel as a filter, not a copy | [Prometheus](https://github.com/Rishikoli/prometheus) | `as_of` |
| Co-citation normalised by Salton's cosine | [PaperGraph](https://github.com/Kevin29Johnson/PaperGraph) | `related_authority` |
| Replaying real incidents, case by case | [WAKE](https://github.com/derealt/wake) | `/replay` |
| An independent implementation checked against the Cypher; mutation tests | Blind Flange, Prometheus, WAKE | `bench/crosscheck.py`, `bench/mutations.py` |
| A contradiction headline with a before/after split | memory-pr | the landing page |

## AI tools

- **Claude Code** (Anthropic) wrote most of the code, tests and documentation, working with the
  team, which reviewed and directed the work.
- **Claude Sonnet**, run through the `claude` CLI, is the *subject* of the agent experiment
  (`bench/agent_experiment.py`): it drafts the briefs that are scored. It also serves as the blinded
  judge in the packet experiment. Every prompt and answer is committed under `bench/results/agent/`.
- No language model decides a Redline verdict. Verdicts are graph queries only.

## When the work was done

<!-- Team: confirm these dates against the hackathon window before submitting. -->
- 2026-11-17: first commit, *v_0 with Relate integration*.
- 2026-11-19 to 11-22: agent experiment and knowledge probe, declarations, CI, Claude Code setup
  (`.mcp.json`, `cite-check` skill), stricter "caution" rule (reliance, not a passing mention).
- 2026-11-26 to 11-27: agent tools (`find_authority`, repairs, `what_if_overruled`,
  `related_authority`, `as_of`), arm D of the agent experiment, landing page, checker at `/app`,
  sanctions replay, Dockerfile, independent cross-check and mutation tests.
