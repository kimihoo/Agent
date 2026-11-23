"""知识库文档上传、检索、切片与删除测试。"""
from __future__ import annotations

from .conftest import auth

CONTENT = (
    "五、印章管理制度\n"
    "公司公章由综合部统一保管。用印需在 OA 系统提交用印申请，"
    "经部门负责人和综合部审批后方可使用。\n"
)


def test_upload_document_is_indexed_and_retrievable(client, tokens):
    headers = auth(tokens["admin"])
    resp = client.post(
        "/api/kbs/5/documents",
        headers=headers,
        files={"file": ("印章管理制度.txt", CONTENT.encode("utf-8"), "text/plain")},
        data={"title": "印章管理制度（测试）"},
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["status"] == "ready"
    assert doc["chunk_count"] >= 1

    answer = client.post(
        "/api/chat/ask",
        headers=headers,
        json={"question": "用印怎么申请？"},
    ).json()
    titles = {citation["doc_title"] for citation in answer["citations"]}
    assert "印章管理制度（测试）" in titles

    text = client.get(f"/api/documents/{doc['id']}/text", headers=headers).json()
    assert "OA 系统提交用印申请" in text["text"]

    deleted = client.delete(f"/api/documents/{doc['id']}", headers=headers)
    assert deleted.status_code == 200

    docs = client.get("/api/kbs/5/documents", headers=headers).json()
    assert all(item["id"] != doc["id"] for item in docs)


def test_upload_rejects_unsupported_type(client, tokens):
    resp = client.post(
        "/api/kbs/5/documents",
        headers=auth(tokens["admin"]),
        files={"file": ("evil.exe", b"binary", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_employee_cannot_write_operations_kb(client, tokens):
    resp = client.post(
        "/api/kbs/5/documents",
        headers=auth(tokens["emp"]),
        files={"file": ("x.txt", CONTENT.encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 403
