from pathlib import Path
import json
import tomllib
from packaging.version import Version
from fastapi.testclient import TestClient
from tarsier import __version__
from tarsier.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_rc_versions_match_pep440_semver_and_about():
    tag = 'v1.0.0-rc1'
    assert Version(__version__) == Version('1.0.0rc1')
    assert tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version'] == __version__
    assert json.loads((ROOT/'frontend/package.json').read_text())['version'] == tag.removeprefix('v')
    assert json.loads((ROOT/'package.json').read_text())['version'] == tag.removeprefix('v')
    lock = json.loads((ROOT/'package-lock.json').read_text())
    assert lock['packages']['frontend']['version'] == tag.removeprefix('v')
    assert TestClient(create_app()).get('/api/about').json()['version'] == tag.removeprefix('v')


def test_reviewed_locks_pin_safe_certifi_and_each_package():
    for minor in ('311','314'):
        text = (ROOT/f'requirements-py{minor}.lock').read_text()
        assert 'certifi==2026.10.23' in text
        assert '--hash=sha256:' in text
        assert 'rc1-evidence' not in text
