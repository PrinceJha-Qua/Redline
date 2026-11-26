"""Redline as MCP tools, so a coding or drafting agent can check citations before it writes them.

    redline mcp                  # stdio, for Claude Code and other local agents
    redline serve                # also served over HTTP at /mcp
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import service

# MCP over HTTP only answers requests addressed to these hosts (protection against DNS rebinding).
# A deployment adds its own name: REDLINE_ALLOWED_HOSTS="redline.example.org,redline.example.org:*"
_HOSTS = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]:*"] + \
         [h.strip() for h in os.getenv("REDLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]

mcp = FastMCP("redline", stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(allowed_hosts=_HOSTS),
              instructions="A citation graph of every Supreme Court case (1754-2014) and every F.3d appeals "
                           "case (1990-2019). Before citing a case from memory, call find_authority with the "
                           "proposition: it returns real cases in the words of the courts that cited them. Call "
                           "check_citations on any text before relying on its citations; for a FABRICATED "
                           "citation, use its suggestions or drop it. UNVERIFIABLE means outside coverage, not "
                           "fake. Never cite a case marked overruled; for caution, read what it stands on.")
mcp.settings.streamable_http_path = "/"


@mcp.tool()
def check_citations(text: str, as_of: str | None = None) -> dict:
    """Check every case citation in `text`. Returns a verdict per citation (VERIFIED, FABRICATED,
    UNVERIFIABLE), its status (good law, caution, overruled), the reason, what it stands on, and for a
    fabricated citation the real cases with that name (`suggestions`). `as_of` (a year or date, such as
    the filing date) asks whether each case was good law then."""
    result = service.check_text(text, as_of)
    for c in result["citations"]:
        c.pop("evidence", None)
    return result


@mcp.tool()
def find_authority(proposition: str, circuit: str | None = None, limit: int = 5, as_of: str | None = None) -> dict:
    """Real cases that courts have cited for `proposition`, each with the courts' own descriptions of it
    ("holding that ..."), its status, and, with `circuit` (such as "Third" or "9th"), that circuit's own
    F.3d opinions saying it. Use this instead of recalling citations from memory."""
    result = service.find_authority(proposition, circuit, limit, as_of)
    result.pop("query", None)
    return result


@mcp.tool()
def related_authority(case_ids: list[str], limit: int = 5) -> list:
    """Good-law cases that courts cite together with `case_ids` (ids such as US:467:837): where to look
    for more authority on the same point."""
    return service.related(case_ids, limit)


@mcp.tool()
def what_if_overruled(case_id: str, text: str | None = None) -> dict:
    """Overrule `case_id` hypothetically: how many decisions rely on it, by court, and which citations in
    `text` would change status. Runs in a rolled-back transaction; the store is never changed."""
    return service.what_if(case_id, text) or {"error": f"No case with id {case_id}."}


@mcp.tool()
def get_case(case_id: str) -> dict:
    """One case by id (such as US:467:837 or F3d:925:1291): status, what overruled it, what it cites
    and what cites it."""
    return service.get_case(case_id) or {"error": f"No case with id {case_id}."}


@mcp.tool()
def search_cases(query: str, limit: int = 10) -> list:
    """Find cases by name, such as "Chevron" or "Loper Bright"."""
    return service.search(query, limit)


@mcp.tool()
def coverage() -> dict:
    """What Redline holds: reporters, volumes, years, counts and sources."""
    return service.get_coverage()
