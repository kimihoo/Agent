"""RAG 问答与流式输出测试。"""
from __future__ import annotations

import json

from .conftest import auth


def test_ask_returns_answer_with_citations(client, tokens):
    resp = client.post(
        "/api/chat/ask",
        headers=auth(tokens["emp"]),
        json={"question": "年假有多少天？"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"].strip()
    assert body["citations"], "答案必须带来源"
    top = body["citations"][0]
    assert top["doc_title"] and top["page"] >= 1
    assert "请假" in top["section"]
    assert top["start_char"] >= 0 and top["end_char"] > top["start_char"]


def test_ask_rejects_empty_question(client, tokens):
    resp = client.post("/api/chat/ask", headers=auth(tokens["emp"]), json={"question": ""})
    assert resp.status_code == 422


def test_stream_emits_expected_events(client, tokens):
    events: list[str] = []
    with client.stream(
        "POST",
        "/api/chat/stream",
        headers=auth(tokens["fin"]),
        json={"question": "报销需要哪些材料？"},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
    assert {"meta", "citations", "token", "done"} <= set(events)


def test_conversation_is_persisted(client, tokens):
    resp = client.post(
        "/api/chat/ask",
        headers=auth(tokens["hr"]),
        json={"question": "请假流程是什么？"},
    )
    conversation_id = resp.json()["conversation_id"]
    detail = client.get(f"/api/conversations/{conversation_id}", headers=auth(tokens["hr"]))
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert any(c["doc_title"] for c in messages[1]["citations"])


def test_restricted_kb_not_used_by_employee(client, tokens):
    """普通员工提问不能命中受限的法务知识库。"""
    body = client.post(
        "/api/chat/ask",
        headers=auth(tokens["emp"]),
        json={"question": "合同付款账期有什么规定？"},
    ).json()
    titles = {c["kb_name"] for c in body["citations"]}
    assert "合同与法务规范库" not in titles
