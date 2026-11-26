"""HTTP API.

    POST /api/check          {"text": "...", "as_of": 2023}  -> verdict for every citation
    GET  /api/suggest?name=  the real cases with a name (the repair for a fabricated citation)
    GET  /api/authority?q=   real cases courts have cited for a proposition (&circuit=3d&as_of=2019)
    GET  /api/related?ids=   cases courts cite together with these
    POST /api/what-if        {"case_id": "...", "text": "..."}  -> overrule a case hypothetically
    GET  /api/case/{id}      one case, its status and neighbours
    GET  /api/search?q=      cases by name
    GET  /api/coverage       what Redline holds (also the health check)
    /mcp                     the same operations as MCP tools
"""
import contextlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import service
from .mcp_server import mcp

WEB = Path(__file__).resolve().parents[1] / "web"


@contextlib.asynccontextmanager
async def lifespan(app):
    service.store()  # open the store before the first request
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Redline", version="0.1.0", lifespan=lifespan)


class CheckRequest(BaseModel):
    text: str = Field(..., description="Brief or memo text containing case citations.")
    suggest: bool = Field(True, description="Look up the real case behind each fabricated citation.")
    as_of: str | int | None = Field(None, description="Check as of this year or date, such as 2023.")


class WhatIfRequest(BaseModel):
    case_id: str = Field(..., description="The case to overrule hypothetically, such as US:545:967.")
    text: str | None = Field(None, description="A brief to re-check under the hypothetical overruling.")


def _bad(e):
    raise HTTPException(413 if "limit" in str(e) else 422, str(e))


@app.post("/api/check")
def api_check(req: CheckRequest):
    try:
        return service.check_text(req.text, req.as_of, req.suggest)
    except ValueError as e:
        _bad(e)


@app.get("/api/suggest")
def api_suggest(name: str):
    """The real cases with this name: the repair for a fabricated citation."""
    return service.suggest(name)


@app.get("/api/authority")
def api_authority(q: str, circuit: str | None = None, limit: int = 5, as_of: str | None = None):
    try:
        return service.find_authority(q, circuit, limit, as_of)
    except ValueError as e:
        _bad(e)


@app.get("/api/related")
def api_related(ids: str, limit: int = 5):
    return service.related([i.strip() for i in ids.split(",")], limit)


@app.post("/api/what-if")
def api_what_if(req: WhatIfRequest):
    try:
        found = service.what_if(req.case_id, req.text)
    except ValueError as e:
        _bad(e)
    if not found:
        raise HTTPException(404, f"No case with id {req.case_id}.")
    return found


@app.get("/api/case/{case_id}")
def api_case(case_id: str):
    found = service.get_case(case_id)
    if not found:
        raise HTTPException(404, f"No case with id {case_id}. Ids look like US:467:837 or F3d:925:1291.")
    return found


@app.get("/api/search")
def api_search(q: str, limit: int = 10):
    return service.search(q, limit)


@app.get("/api/coverage")
def api_coverage():
    return service.get_coverage()


app.mount("/mcp", mcp.streamable_http_app())

if WEB.is_dir():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / ("index.html" if (WEB / "index.html").exists() else "app.html"))

    @app.get("/app", include_in_schema=False)
    def checker():
        return FileResponse(WEB / "app.html")
