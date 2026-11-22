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
| Full-text index (`case_name`), queried with `db.index.fulltext.queryNodes` | `redline/service.py`, `bench/agent_experiment.py` |
| One connection per thread, owned by a worker that serves the web app and the MCP server | `redline/store.py` |

## Third-party code and data

| Name | Use | Licence |
|---|---|---|
| eyecite, reporters-db (Free Law Project) | Finding citations in text; the list of real reporter series | BSD |
| FastAPI, Uvicorn | Web app and HTTP API | MIT / BSD |
| MCP Python SDK | MCP server (stdio and HTTP) | MIT |
| pytest, httpx | Tests | MIT / BSD |
| Caselaw Access Project, Harvard Law School Library | Every case, page range and citation in the store | Released without restriction |
| Wikipedia, *List of overruled United States Supreme Court decisions* | The 144 overrulings | CC BY-SA 4.0 |
| Fowler & Jeon, *The Authority of Supreme Court Precedent* (2008) | Method only: HITS authority scores, implemented in `ingest/build_store.py` | — |
| LePhantomCite (Princeton, 2026) | Benchmark data, downloaded by `make bench`, not redistributed | See the dataset |

No code was copied from other hackathon entries. One idea was: the agent experiment's three arms
(plain / "be careful" warning / tool) follow the design of
[Precedent](https://github.com/ZNLong2203/precedent), another entry.

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
