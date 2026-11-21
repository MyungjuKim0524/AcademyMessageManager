import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/contract/message-preview-cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
client = TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_message_preview_contract_fixture(case: dict) -> None:
    response = client.post(
        "/api/messages/preview",
        content=json.dumps(case["body"], ensure_ascii=False).encode(),
        headers={"content-type": case["contentType"]},
    )
    assert response.status_code == case["expectedStatus"]
    assert response.json() == case["expectedBody"]
