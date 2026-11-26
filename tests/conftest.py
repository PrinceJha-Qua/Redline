import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """One app client per run: the MCP session manager starts once per process."""
    from redline.api import app
    with TestClient(app, base_url="http://localhost:8000") as c:
        yield c
