"""Read-only About information, project documents and license files."""

from pathlib import Path
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from tarsier import __version__

router = APIRouter(prefix="/api/about")

_RESOURCES = {
    "LICENSE": ("LICENSE (Apache-2.0)", "text/plain"),
    "THIRD_PARTY_NOTICES": ("Third-party licenses and notices", "text/markdown"),
}


def _about_file(relative: str) -> Path:
    """A bundled copy in an installed package, otherwise the file in the source tree."""
    packaged = Path(__file__).resolve().parents[1] / "web" / "about" / relative
    return packaged if packaged.exists() else Path(__file__).resolve().parents[2] / relative


def _project_docs() -> list[str]:
    folder = _about_file("docs")
    return sorted(p.name for p in folder.glob("*.md")) if folder.is_dir() else []


@router.get("")
def get_about() -> dict:
    return {
        # Keep the package's PEP 440 version as the only source of truth, while
        # displaying prereleases in the same form used by npm and the release tag.
        "version": re.sub(r"(a|b|rc)(\d+)$", r"-\1\2", __version__),
        "license": "Apache-2.0",
        "links": [
            {"label": label, "href": f"/api/about/resources/{name}"}
            for name, (label, _media_type) in _RESOURCES.items()
        ] + [
            {"label": name.removesuffix(".md"), "href": f"/api/about/resources/docs/{name}"}
            for name in _project_docs()
        ],
    }


@router.get("/resources/{name}")
def get_about_resource(name: str):
    resource = _RESOURCES.get(name)
    if resource is None:
        raise HTTPException(status_code=404, detail="Project document not found.")

    path = Path(__file__).resolve().parents[1] / "web" / "about" / name
    if not path.is_file():
        repo = Path(__file__).resolve().parents[2]
        path = repo / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Project document is unavailable.")
    return FileResponse(path, media_type=resource[1])


@router.get("/resources/docs/{name}")
def get_project_doc(name: str):
    # Only a name that is already in the list: no path can be built from the request.
    if name not in _project_docs():
        raise HTTPException(status_code=404, detail="Project document not found.")
    return FileResponse(_about_file("docs") / name, media_type="text/plain; charset=utf-8")


@router.get("/resources/third_party_licenses/texts/{digest}")
def get_third_party_license_text(digest: str):
    if not re.fullmatch(r"[a-f0-9]{16}\.txt", digest):
        raise HTTPException(status_code=404, detail="License text not found.")
    root = Path(__file__).resolve().parents[1] / "web" / "about"
    path = root / "third_party_licenses" / "texts" / digest
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / "third_party_licenses" / "texts" / digest
    if not path.is_file():
        raise HTTPException(status_code=404, detail="License text not found.")
    return FileResponse(path, media_type="text/plain")
