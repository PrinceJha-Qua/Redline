"""HTTP API.

    POST /api/check          {"text": "..."}  -> verdict for every citation
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


@app.post("/api/check")
def api_check(req: CheckRequest):
    try:
        return service.check_text(req.text)
    except ValueError as e:
        raise HTTPException(413, str(e))


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
        return FileResponse(WEB / "index.html")
