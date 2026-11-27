# Redline: Devpost submission

Each section below matches a field on the Devpost form.

---

## Elevator pitch

Redline catches fabricated and overruled case citations before you file, checking every citation in a brief against a Relate graph of 170,651 US cases, entirely on your machine.

---

## Project story

### Inspiration

In *Mata v. Avianca* (S.D.N.Y. 2023), two lawyers filed a brief citing *Varghese v. China Southern Airlines*, 925 F.3d 1339. The case does not exist; an AI tool had invented it, and the court sanctioned the lawyers. *Mata* was the first well-known case, not the last. By June 2026, US courts had dealt with 1,058 cases involving AI-hallucinated content.

What struck us is that a fake citation is not a matter of opinion. A citation is a pointer to a page in a printed book. If you know which case occupies every page of every volume, you can prove that a citation points at someone else's case. That is a graph problem, so we built a graph.

A real citation can also mislead. *Chevron* was overruled in 2024, yet thousands of appellate decisions still rest on it. A brief that relies on them is relying on law that no longer exists. We wanted a tool that catches both problems and shows its evidence for every verdict.

### What it does

Paste a brief, and Redline gives every citation one of three verdicts:

- **Fabricated.** The citation cannot be correct. For *Varghese*, Redline reports: *"Page 1339 of 925 F.3d is inside J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019), which runs from page 1291 to 1349. No case named Varghese is in volume 925."*
- **Verified**, with a status: **good law**, **overruled**, or **caution**. Caution means the case relies on a decision that was later overruled; Redline shows the chain and quotes the court's own words about the case it relied on.
- **Unverifiable.** The citation falls outside Redline's data. Redline never calls such a citation fake.

Every verdict comes from a graph query, and the interface shows the Cypher behind it. No language model decides a verdict.

Redline also repairs what it flags. A fabricated citation comes with the real case of that name when one exists: Claude Sonnet cited *Campbell v. Air Jamaica* at 863 F.3d 1255, and Redline offers 760 F.3d 1165, one click away. Given a filing year, Redline judges by the law of that day, so a 2023 brief citing *Chevron* cited good law. And it answers "what if": overrule any Supreme Court case hypothetically, and Redline shows who relied on it, by court, and what changes in your brief.

**For agents.** An AI drafter invents citations because it cites from memory, so Redline gives it a graph to cite from. `find_authority` takes a proposition and returns real cases, each described in the words of the courts that cited them, together with that circuit's own opinions. For "temporal proximity alone is insufficient to show retaliation" in the Third Circuit, it returns *Clark County School District v. Breeden* and the Third Circuit's *LeBoon v. Lancaster Jewish Community Center*, 503 F.3d 217.

Redline runs as a web app, a command-line tool (`redline check brief.txt` exits with an error if anything is fabricated), an HTTP API, and a set of MCP tools, so an AI drafting agent can check its own citations before it commits to them. Claude Code picks the tools up automatically from the repository's `.mcp.json`, together with a `cite-check` skill that tells the agent how to act on each verdict.

### How we built it

**The graph.** We built the store from the Caselaw Access Project (Harvard Law School Library): every *United States Reports* case to 2014 and every *Federal Reporter, Third Series* case from 1990 to 2019. Overrulings come from the Library of Congress list as published on Wikipedia.

```
(:Reporter)-[:HAS_VOLUME]->(:Volume)-[:CONTAINS]->(:Case {first_page, last_page})
(:Case)-[:CITES {weight, parenthetical}]->(:Case)       983,247 citations
(:Case)-[:OVERRULES {partial}]->(:Case)                 144 overrulings
(:Citation {text: "93 S.Ct. 705"})-[:CITATION_OF]->(:Case)
```

Two relationships do the work. **Volume → case page ranges** prove a fabrication: the graph knows which case owns each page. **Case → cites → case ← overrules ← case** reveals what a real citation stands on.

**Relate.** The store is a Relate directory of Parquet files (51.6 MB), committed to the repository and opened read-only, in process. Redline uses constraints, a property index, and Cypher throughout, from `UNWIND` bulk loading to multi-hop traversals. Two Relate features carry the agent tools. A full-text index on a *relationship* property, the 241,801 parentheticals courts wrote about the cases they cite, is what `find_authority` searches. And a read-only connection still accepts writes inside a transaction, answers queries against them, and refuses to commit: the what-if writes a hypothetical overruling, runs the production checker against it, and rolls back, leaving the committed store byte-for-byte unchanged. Relate connections are bound to the thread that opened them, so the web server and the MCP server route every query through one worker thread that owns the connection. Checking a brief takes 17–45 ms, and finding every case within two citation hops of *Chevron* (18,224 cases) takes 14 ms.

**Authority.** Every case carries a HITS authority score computed over the citation graph, the measure Fowler and Jeon applied to Supreme Court precedent:

$$a(v) = \sum_{u \to v} h(u), \qquad h(u) = \sum_{u \to v} a(v)$$

**Stack.** Python, eyecite for finding citations in text, FastAPI for the web app and API, and the MCP Python SDK. Claude Code wrote much of the code, under our direction and review.

### Does it work?

Every number below is regenerated by `make bench`, and we publish first-run errors alongside current results.

- **It rarely cries wolf.** On a fresh sample of 495 published opinions that it had never seen, Redline's first run called \\( 9 \\) of \\( 31{,}877 \\) real citations fabricated (0.028%). Each of those errors led to a fix. Across both samples, 60,431 real citations, it now calls none of them fake; every remaining flag points at a genuine error in the digitized text.
- **It holds up on an outside benchmark.** On LePhantomCite (Princeton, 2026), Redline caught every citation to a reporter series that was never published (129 of 129) and every non-existent citation within its coverage (104 of 104 on the held-out split), with no unexplained false alarms.
- **It works on real sanctions cases.** Of 86 citations that US courts found fabricated and that fall within Redline's data, it proves 47 fake from page evidence alone.
- **It helps an AI drafter, and a warning alone does not.** We gave Claude Sonnet 24 drafting tasks that ask for circuit authority from memory, the situation in *Mata*, three times each under four conditions (288 briefs, 4,426 citations). Briefs containing a citation Redline proves wrong: 4 of 72 with no help, 5 of 72 with an explicit warning to verify every citation, 2 of 72 with Redline's checker over MCP, and **0 of 72** (0 of 935 citations) with the checker plus `find_authority`. The full toolset costs about four times as much per brief, and the sample is small: the difference is not statistically significant (p = 0.25 against the warning), so we present it as a direction, not a proof.
- **It would have caught real sanctioned filings.** Of 66 sanctioned filings with a citation in Redline's data, 38 contain one that Redline proves fabricated. A replay page shows every filing, Redline's evidence, and the court's own words.
- **A second implementation agrees.** A plain-Python reader of the store's Parquet files, with no Relate and no Cypher, recomputed which case owns each page (264,100 lookups) and what every case stands on (15,685 cases): zero disagreements. Mutation testing removes each of 12 safeguards in turn, and the test suite catches all 12.
- **Models do not know what has been overruled.** Asked without tools, Claude Sonnet said 26 of the 142 overruled Supreme Court decisions in our graph were still good law. Those decisions are cited by 1,137 federal appellate opinions. Some misses are arguable (*Teague v. Lane* was overruled only in part), and every answer is published.
- **We report what did not work.** We first tested famous overruled doctrines (*Chevron*, *Saucier*, *Abood*) with research packets full of stale law. The model already knew those overrulings and relied on none of them in any condition, so that design could not show a difference. We published it as a null result.

### Challenges we ran into

- **The source data is imperfect.** Some volumes in the Harvard data are missing cases, and a few have shifted page numbers. Redline audits its own data against how courts actually cite it: 4,056 pages that courts cite as the start of a case have no case in the data. Redline protects those pages and refuses to use suspect volumes as proof.
- **Precision matters more than recall.** A wrong "fabricated" verdict is worse than a missed one. A short name Redline cannot match, an "In re" caption, or a page after a volume's last opinion therefore comes back unverifiable, not fake.
- **"Caution" was too loud at first.** *United States v. Lopez*, a Commerce Clause case, cites *Planned Parenthood v. Casey* once and was flagged yellow. Caution now requires genuine reliance: more than one citation, or a parenthetical that explains the citation. A passing mention is shown but not flagged. Of 141,484 appellate cases, 9,194 cite a later-overruled Supreme Court case, and 5,342 rely on one, 2,616 of them on *Chevron*.
- **Measuring an agent honestly is hard.** Our first experiment design produced no signal, and our first audit of the flagged citations missed a real case filed under an abbreviated name. Both lessons are recorded in the benchmark report.

### Accomplishments that we're proud of

- Zero false fabrication verdicts across 60,431 real citations, with the first-run errors published.
- Every verdict is explainable as a single Cypher query that anyone can rerun against the committed store, and an independent implementation agrees with every answer it checked.
- With Redline's tools, Claude Sonnet filed 72 briefs and 935 citations without a single citation Redline could prove wrong.
- The entire graph lives in the repository: clone it, and it runs with no download, server, or API key.

### What we learned

A citation is a pointer, and pointers belong in a graph. Once case law is modeled as volumes, pages, and citations, questions that sound like legal judgment ("does this case exist?", "is it still good law?") become traversals. We also learned that a claim of zero false alarms is only credible when the misses, the first runs, and the null results are published next to it.

### What's next

- Read negative treatment directly from opinion text ("abrogated by", "overruled in part") and measure it against the CaseHOLD Overruling task, extending coverage beyond 144 Supreme Court overrulings.
- A public hosted copy for anyone to try, and Relate compiled to WebAssembly for a version that runs entirely in the browser.
- Matter-wide what-ifs: one overruling checked against every brief in a matter at once.
- Coverage of F.4th, F. Supp., and state reporters.

---

## Built with

relate, neo4j, cypher, python, fastapi, uvicorn, model-context-protocol, eyecite, reporters-db, caselaw-access-project, parquet, pyarrow, docker, claude-code, claude, javascript, html, css, pytest, uv, github-actions

---

## Which Relate mode does your project use?

Directory

## Path to the persistent store in your repo

`data/redline-us/`

## Why did you choose this mode?

The directory store is 51.6 MB of Parquet files, none larger than 50 MB, so the whole graph can be committed and judges can clone and inspect it without a download; the same graph as a single `.rl` file measured about eight times larger. Redline opens it read-only and in process, so a firm's draft briefs never leave the machine.

---

## Before you submit

- [ ] Add the GitHub topics `relate` (required) and `relate-neo4j-hackathon` to the repository.
- [ ] Make the repository public.
- [ ] Record the 1–2 minute demo video.
- [ ] Confirm the dates in `docs/DECLARATIONS.md` against the hackathon window.
