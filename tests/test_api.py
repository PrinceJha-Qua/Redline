"""Phase 2: the HTTP API and MCP tools answer, and checking never changes the store."""
import hashlib
import json
from pathlib import Path

import pytest

from redline.store import store_path

BRIEFS = Path(__file__).parent / "fixtures" / "briefs"


def store_hash():
    h = hashlib.sha256()
    for f in sorted(p for p in store_path().rglob("*") if p.is_file()):
        h.update(f.relative_to(store_path()).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def test_check_and_store_unchanged(client):
    before = store_hash()
    for brief in sorted(BRIEFS.glob("*.txt")):
        r = client.post("/api/check", json={"text": brief.read_text()})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["summary"]["citations"] == len(body["citations"]) > 0
        for c in body["citations"]:
            assert c["verdict"] in {"VERIFIED", "FABRICATED", "UNVERIFIABLE"}
            assert c["reason"]
            assert c["span"][1] > c["span"][0]
    assert store_hash() == before


def test_case(client):
    body = client.get("/api/case/US:410:113").json()
    assert body["case"]["name"] == "Roe v. Wade" and body["status"] == "overruled"
    assert body["overruled_by"][0]["name"].startswith("Dobbs")
    assert client.get("/api/case/US:1:99999").status_code == 404


def test_search(client):
    rows = client.get("/api/search", params={"q": "Chevron"}).json()
    assert rows[0]["id"] == "US:467:837"
    assert client.get("/api/search", params={"q": "!!"}).json() == []


def test_coverage(client):
    body = client.get("/api/coverage").json()
    assert body["engine"] == "Relate"
    assert {r["abbr"] for r in body["reporters"]} == {"U.S.", "F.3d"}
    assert body["cases"] == 170651


def test_mcp_lists_and_calls_tools(client):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}}
    assert client.post("/mcp/", json=init, headers=headers).status_code == 200
    tools = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers).json()
    assert {t["name"] for t in tools["result"]["tools"]} == {"check_citations", "get_case", "search_cases", "coverage",
                                                                  "find_authority", "related_authority", "what_if_overruled"}
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "check_citations", "arguments": {"text": "Varghese v. China S. Airlines, 925 F.3d 1339 (11th Cir. 2019)."}}}
    body = client.post("/mcp/", json=call, headers=headers).json()
    result = json.loads(body["result"]["content"][0]["text"])
    assert result["citations"][0]["verdict"] == "FABRICATED"
