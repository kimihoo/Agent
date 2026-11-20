"""请求体与响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class KBIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    department: str = "综合部"
    visibility: str = "internal"


class KBPermissionIn(BaseModel):
    principal_type: str  # user/role/department
    principal: str
    permission: str = "read"


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    kb_ids: list[int] = Field(default_factory=list)


class RiskDisposition(BaseModel):
    status: str  # accepted/ignored/fixed
    note: str = ""


class ReviewIn(BaseModel):
    decision: str  # approve/reject/changes
    comment: str = ""


class UserIn(BaseModel):
    username: str
    password: str
    display_name: str
    department: str = "综合部"
    role: str = "employee"


class UserPatch(BaseModel):
    display_name: str | None = None
    department: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


class RuleIn(BaseModel):
    code: str
    name: str
    category: str = "条款完整性"
    severity: str = "medium"
    kind: str
    params: dict = Field(default_factory=dict)
    message: str
    legal_basis: str = ""
    enabled: bool = True
