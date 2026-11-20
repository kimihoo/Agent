"""认证接口测试。"""
from __future__ import annotations

from .conftest import auth


def test_login_all_demo_accounts(client):
    for username in ("admin", "hr", "fin", "legal", "emp"):
        resp = client.post("/api/auth/login", json={"username": username, "password": f"{username}123"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token"] and body["user"]["username"] == username


def test_login_rejects_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code in (401, 403)


def test_me_returns_profile(client, tokens):
    resp = client.get("/api/auth/me", headers=auth(tokens["legal"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "legal" and body["department"] == "法务部"
