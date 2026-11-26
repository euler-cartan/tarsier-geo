"""TRS-109: the license and the project documents open from About."""

import tomllib
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tarsier.api.about import router

ROOT = Path(__file__).resolve().parents[2]
SIX = ["DVS", "FSD", "FTL", "PRD", "TAD", "WFD"]


def test_about_lists_opens_and_bundles_the_project_documents():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    links = {link["label"]: link["href"] for link in client.get("/api/about").json()["links"]}
    assert set(SIX) <= set(links)
    for name in SIX:
        response = client.get(links[name])
        assert response.status_code == 200
        assert response.content == (ROOT / "docs" / f"{name}.md").read_bytes()
    assert client.get("/api/about/resources/LICENSE").status_code == 200
    for bad in ("missing.md", "..%2FREADME.md", "..%5CREADME.md"):
        assert client.get(f"/api/about/resources/docs/{bad}").status_code == 404

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    bundled = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for document in (ROOT / "docs").glob("*.md"):
        assert bundled.get(f"docs/{document.name}") == f"tarsier/web/about/docs/{document.name}"
