"""身份与知识库权限测试。"""
from __future__ import annotations

from .conftest import auth


def test_admin_sees_all_knowledge_bases(client, tokens):
    kbs = client.get("/api/kbs", headers=auth(tokens["admin"])).json()
    assert len(kbs) == 5


def test_employee_cannot_see_restricted_kb(client, tokens):
    kbs = client.get("/api/kbs", headers=auth(tokens["emp"])).json()
    ids = {kb["id"] for kb in kbs}
    assert ids == {1, 2, 3, 5}
    assert 4 not in ids


def test_employee_cannot_create_kb(client, tokens):
    resp = client.post(
        "/api/kbs",
        headers=auth(tokens["emp"]),
        json={"name": "临时库", "description": "", "department": "市场部", "visibility": "internal"},
    )
    assert resp.status_code == 403


def test_employee_cannot_read_restricted_kb_documents(client, tokens):
    resp = client.get("/api/kbs/4/documents", headers=auth(tokens["emp"]))
    assert resp.status_code == 403


def test_employee_cannot_see_contracts(client, tokens):
    resp = client.get("/api/contracts", headers=auth(tokens["emp"]))
    assert resp.status_code == 200 and resp.json() == []


def test_employee_cannot_submit_review(client, tokens):
    detail = client.get("/api/contracts/1", headers=auth(tokens["admin"])).json()
    assert detail["can_review"] is True
    resp = client.post(
        "/api/contracts/1/review",
        headers=auth(tokens["emp"]),
        json={"decision": "approve", "comment": ""},
    )
    assert resp.status_code == 403
