PY ?= .venv/bin/python

.PHONY: setup fetch data pack test run bench scale clean

setup:            ## create the virtualenv and install Redline
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

fetch:            ## download the public source data (about 2.4 GB, resumable)
	$(PY) -m ingest.fetch_cap us f3d
	$(PY) -m ingest.overrulings

data: fetch       ## build the core store: data/redline-us/
	$(PY) bench/pagemap_audit.py
	$(PY) -m ingest.build_store --pack core

pack: fetch       ## build the federal pack: data/packs/redline-federal/
	$(PY) bench/pagemap_audit.py
	$(PY) -m ingest.build_store --pack federal

test:
	$(PY) -m pytest -q

run:              ## web app, API and MCP on http://127.0.0.1:8000
	.venv/bin/redline serve

bench:            ## every benchmark, then docs/BENCHMARK.md (downloads the datasets once)
	$(PY) bench/phantom.py eval
	$(PY) bench/phantom.py aux_train
	$(PY) bench/false_alarms.py
	$(PY) bench/wild.py
	$(PY) bench/report.py

scale:            ## time the multi-hop queries on a store
	$(PY) bench/scale.py $(STORE)

clean:
	rm -rf data/scratch
