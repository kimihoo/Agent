"""合同结构化抽取、规则校验与人工复核测试。"""
from __future__ import annotations

from .conftest import auth


def test_sample_contract_has_structured_analysis(client, tokens):
    contracts = client.get("/api/contracts", headers=auth(tokens["admin"])).json()
    assert len(contracts) == 1
    contract_id = contracts[0]["id"]

    detail = client.get(f"/api/contracts/{contract_id}", headers=auth(tokens["admin"])).json()
    assert detail["status"] == "pending_review"
    assert detail["amount"] == 480000
    assert detail["counterparty"] == "智维信息技术有限公司"
    assert detail["risk_level"] == "high"
    assert len(detail["clauses"]) >= 6

    codes = {risk["rule_code"] for risk in detail["risks"]}
    assert {"R013", "R014", "R011", "R012"} <= codes


def test_approve_blocked_until_high_risks_disposed(client, tokens):
    headers = auth(tokens["legal"])
    detail = client.get("/api/contracts/1", headers=headers).json()

    resp = client.post(
        "/api/contracts/1/review",
        headers=headers,
        json={"decision": "approve", "comment": "同意"},
    )
    assert resp.status_code == 400
    assert "高风险" in resp.json()["detail"]

    for risk in detail["risks"]:
        if risk["status"] == "open":
            patched = client.patch(
                f"/api/contracts/1/risks/{risk['id']}",
                headers=headers,
                json={"status": "accepted", "note": "业务已确认可接受"},
            )
            assert patched.status_code == 200

    still_blocked = client.get("/api/contracts/1", headers=headers).json()
    assert all(risk["status"] != "open" for risk in still_blocked["risks"])


def test_reject_requires_comment(client, tokens):
    resp = client.post(
        "/api/contracts/1/review",
        headers=auth(tokens["legal"]),
        json={"decision": "changes", "comment": "   "},
    )
    assert resp.status_code == 400


def test_approve_after_disposition(client, tokens):
    resp = client.post(
        "/api/contracts/1/review",
        headers=auth(tokens["legal"]),
        json={"decision": "approve", "comment": "高风险已处置，同意签署"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["tasks"][0]["decision"] == "approve"


def test_non_reviewer_cannot_dispose_risk(client, tokens):
    resp = client.patch(
        "/api/contracts/1/risks/1",
        headers=auth(tokens["fin"]),
        json={"status": "ignored", "note": ""},
    )
    assert resp.status_code == 403
