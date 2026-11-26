from pathlib import Path
import re
from fastapi.testclient import TestClient
from tarsier.api.app import create_app


def test_bundled_notices_and_license_texts_are_served():
    client = TestClient(create_app())
    about = client.get('/api/about').json()
    assert any(link['label'] == 'Third-party licenses and notices' for link in about['links'])
    result = client.get('/api/about/resources/THIRD_PARTY_NOTICES')
    assert result.status_code == 200
    assert 'Inter' in result.text and 'Newsreader' in result.text
    assert 'LGPL' in result.text and 'MPL' in result.text and 'OFL' in result.text
    digest = re.search(r'third_party_licenses/texts/([a-f0-9]{16}\.txt)', result.text).group(1)
    text = client.get('/api/about/resources/third_party_licenses/texts/' + digest)
    assert text.status_code == 200 and text.text
    assert client.get('/api/about/resources/third_party_licenses/texts/not-a-license.txt').status_code in (400, 404)
