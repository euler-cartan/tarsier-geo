from pathlib import Path


def test_security_reporting_has_private_steps_and_unset_contact():
    text = (Path(__file__).resolve().parents[2]/'SECURITY.md').read_text()
    assert 'Security' in text and 'Report a vulnerability' in text
    assert 'datumlabs@eulercartan.com' in text
    assert 'Supported versions' in text
    assert 'public issue' in text
