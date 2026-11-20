"""测试夹具：使用独立临时数据目录，避免污染演示数据库。"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="kb-test-")
os.environ["DATA_DIR"] = _TMP_DIR
os.environ["SECRET_KEY"] = "test-only-secret"
# 强制使用本地兜底模型，保证离线可测试
for _key in ("LLM_BASE_URL", "LLM_API_KEY", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY"):
    os.environ.pop(_key, None)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def tokens(client: TestClient) -> dict[str, str]:
    result: dict[str, str] = {}
    for username, password in (
        ("admin", "admin123"),
        ("hr", "hr123"),
        ("fin", "fin123"),
        ("legal", "legal123"),
        ("emp", "emp123"),
    ):
        resp = client.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        result[username] = resp.json()["token"]
    return result


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
