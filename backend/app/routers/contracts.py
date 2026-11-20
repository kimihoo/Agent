"""合同上传、结构化分析、规则校验与人工复核。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import get_db
from ..models import Contract, ContractClause, ContractRisk, ReviewTask, Rule, User
from ..schemas import ReviewIn, RiskDisposition, RuleIn
from ..security import get_current_user, require_admin
from ..services.audit import log
from ..services.contracts import (
    CLAUSE_TYPES,
    apply_llm_fields,
    evaluate_rules,
    extract_clauses,
    extract_fields,
    llm_extract,
    risk_score,
    summarize,
)
from ..services.parser import parse_file
from ..services.permissions import can_review_contract, can_view_contract

router = APIRouter(prefix="/api", tags=["contracts"])

ALLOWED_SUFFIX = {"pdf", "docx", "txt", "md", "markdown"}
MAX_SIZE = 25 * 1024 * 1024
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def analyze_contract(db: Session, contract: Contract, text: str) -> None:
    db.query(ContractClause).filter(ContractClause.contract_id == contract.id).delete()
    db.query(ContractRisk).filter(ContractRisk.contract_id == contract.id).delete()
    db.flush()

    clause_rows: list[ContractClause] = []
    for item in extract_clauses(text):
        clause_rows.append(ContractClause(contract_id=contract.id, **item))
    db.add_all(clause_rows)
    db.flush()

    fields = extract_fields(text)
    payload = llm_extract(text)
    if payload:
        fields = apply_llm_fields(fields, payload)
        for clause in payload.get("clauses") or []:
            clause_type = clause.get("clause_type")
            if clause_type in CLAUSE_TYPES and clause_type not in {row.clause_type for row in clause_rows}:
                content = (clause.get("content") or "").strip()
                if content:
                    db.add(ContractClause(
                        contract_id=contract.id,
                        clause_type=clause_type,
                        heading=(clause.get("heading") or CLAUSE_TYPES[clause_type]["name"])[:200],
                        content=content[:2000],
                        confidence=0.8,
                        extractor="llm",
                    ))
        db.flush()

    contract.contract_no = str(fields.get("contract_no") or "")[:120]
    contract.counterparty = str(fields.get("counterparty") or fields.get("乙方") or "")[:200]
    contract.amount = fields.get("amount")

    clause_map = {row.clause_type: row.content for row in
                  db.execute(select(ContractClause).where(ContractClause.contract_id == contract.id)).scalars()}
    risks = evaluate_rules(db, text, clause_map, fields, contract)
    db.add_all(risks)
    db.flush()

    contract.risk_score, contract.risk_level = risk_score(risks)
    clauses = db.execute(select(ContractClause).where(ContractClause.contract_id == contract.id)).scalars().all()
    contract.summary = summarize(contract, risks, clauses)
    contract.status = "pending_review"

    if not contract.tasks or all(task.status == "completed" for task in contract.tasks):
        db.add(ReviewTask(contract_id=contract.id, created_by=contract.uploaded_by))


def _detail(db: Session, contract: Contract, user: User) -> dict:
    clauses = db.execute(
        select(ContractClause).where(ContractClause.contract_id == contract.id)
    ).scalars().all()
    risks = db.execute(
        select(ContractRisk).where(ContractRisk.contract_id == contract.id)
    ).scalars().all()
    tasks = db.execute(
        select(ReviewTask).where(ReviewTask.contract_id == contract.id).order_by(ReviewTask.id.desc())
    ).scalars().all()
    risks.sort(key=lambda risk: (SEVERITY_ORDER.get(risk.severity, 9), risk.rule_code))
    uploader = db.get(User, contract.uploaded_by) if contract.uploaded_by else None
    return {
        "id": contract.id,
        "title": contract.title,
        "filename": contract.filename,
        "contract_no": contract.contract_no,
        "counterparty": contract.counterparty,
        "amount": contract.amount,
        "currency": contract.currency,
        "status": contract.status,
        "risk_score": contract.risk_score,
        "risk_level": contract.risk_level,
        "summary": contract.summary,
        "uploaded_by": uploader.display_name if uploader else "",
        "created_at": contract.created_at.isoformat(),
        "updated_at": contract.updated_at.isoformat(),
        "can_review": can_review_contract(user),
        "clauses": [
            {
                "id": clause.id,
                "clause_type": clause.clause_type,
                "clause_name": CLAUSE_TYPES.get(clause.clause_type, {}).get("name", clause.clause_type),
                "heading": clause.heading,
                "content": clause.content,
                "confidence": round(clause.confidence, 2),
                "extractor": clause.extractor,
            }
            for clause in sorted(clauses, key=lambda c: c.clause_type)
        ],
        "risks": [
            {
                "id": risk.id,
                "rule_code": risk.rule_code,
                "name": risk.name,
                "severity": risk.severity,
                "message": risk.message,
                "evidence": risk.evidence,
                "clause_type": risk.clause_type,
                "status": risk.status,
                "note": risk.note,
                "handled_at": risk.handled_at.isoformat() if risk.handled_at else None,
            }
            for risk in risks
        ],
        "tasks": [
            {
                "id": task.id,
                "status": task.status,
                "decision": task.decision,
                "comment": task.comment,
                "reviewer_id": task.reviewer_id,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ],
    }


@router.post("/contracts")
def upload_contract(
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filename = file.filename or "未命名合同"
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(400, f"仅支持 {', '.join(sorted(ALLOWED_SUFFIX))} 格式")
    data = file.file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "文件超过 25MB 限制")
    if not data:
        raise HTTPException(400, "文件内容为空")

    stored = UPLOAD_DIR / f"contract_{uuid.uuid4().hex}.{suffix}"
    stored.write_bytes(data)
    try:
        parsed = parse_file(stored, filename)
    except Exception as exc:  # noqa: BLE001
        stored.unlink(missing_ok=True)
        raise HTTPException(400, f"合同解析失败：{exc}")
    if len(parsed.full_text.strip()) < 50:
        stored.unlink(missing_ok=True)
        raise HTTPException(400, "合同正文内容过少，无法分析")

    contract = Contract(
        title=(title or filename.rsplit(".", 1)[0]).strip()[:200],
        filename=filename,
        stored_path=str(stored),
        status="analyzing",
        uploaded_by=user.id,
    )
    db.add(contract)
    db.commit()

    analyze_contract(db, contract, parsed.full_text)
    log(db, user.id, "contract.analyze", "contract", contract.id,
        f"{contract.title} 风险分 {contract.risk_score}")
    db.commit()
    return _detail(db, contract, user)


@router.get("/contracts")
def list_contracts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Contract).order_by(Contract.created_at.desc())
    if user.role not in ("admin", "legal", "finance"):
        query = query.where(Contract.uploaded_by == user.id)
    contracts = db.execute(query).scalars().all()
    result = []
    for contract in contracts:
        counts = {"high": 0, "medium": 0, "low": 0}
        for risk in db.execute(
            select(ContractRisk).where(ContractRisk.contract_id == contract.id)
        ).scalars():
            counts[risk.severity] = counts.get(risk.severity, 0) + 1
        result.append({
            "id": contract.id,
            "title": contract.title,
            "counterparty": contract.counterparty,
            "amount": contract.amount,
            "status": contract.status,
            "risk_score": contract.risk_score,
            "risk_level": contract.risk_level,
            "risk_counts": counts,
            "created_at": contract.created_at.isoformat(),
        })
    return result


@router.get("/contracts/{contract_id}")
def get_contract(contract_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "合同不存在")
    if not can_view_contract(user, contract):
        raise HTTPException(403, "没有查看该合同的权限")
    return _detail(db, contract, user)


@router.post("/contracts/{contract_id}/reanalyze")
def reanalyze(contract_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "合同不存在")
    if not can_review_contract(user) and contract.uploaded_by != user.id:
        raise HTTPException(403, "没有重新分析的权限")
    try:
        parsed = parse_file(Path(contract.stored_path), contract.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"合同解析失败：{exc}")
    analyze_contract(db, contract, parsed.full_text)
    log(db, user.id, "contract.reanalyze", "contract", contract.id, contract.title)
    db.commit()
    return _detail(db, contract, user)


@router.patch("/contracts/{contract_id}/risks/{risk_id}")
def dispose_risk(contract_id: int, risk_id: int, payload: RiskDisposition,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not can_review_contract(user):
        raise HTTPException(403, "仅法务或管理员可以处置风险项")
    risk = db.get(ContractRisk, risk_id)
    if not risk or risk.contract_id != contract_id:
        raise HTTPException(404, "风险项不存在")
    if payload.status not in ("open", "accepted", "ignored", "fixed"):
        raise HTTPException(400, "状态仅支持 open/accepted/ignored/fixed")
    risk.status = payload.status
    risk.note = payload.note[:1000]
    risk.handled_by = user.id if payload.status != "open" else None
    risk.handled_at = datetime.now() if payload.status != "open" else None
    log(db, user.id, "contract.risk_dispose", "risk", risk.id, f"{risk.rule_code}:{payload.status}")
    db.commit()
    return {"ok": True}


@router.post("/contracts/{contract_id}/review")
def submit_review(contract_id: int, payload: ReviewIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    if not can_review_contract(user):
        raise HTTPException(403, "仅法务或管理员可以提交复核意见")
    contract = db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(404, "合同不存在")
    if payload.decision not in ("approve", "reject", "changes"):
        raise HTTPException(400, "decision 仅支持 approve/reject/changes")

    risks = db.execute(
        select(ContractRisk).where(ContractRisk.contract_id == contract_id)
    ).scalars().all()
    open_high = [risk for risk in risks if risk.severity == "high" and risk.status == "open"]
    if payload.decision == "approve" and open_high:
        codes = "、".join(risk.rule_code for risk in open_high)
        raise HTTPException(400, f"仍有 {len(open_high)} 项高风险未处置（{codes}），不能直接通过")
    if payload.decision in ("reject", "changes") and not payload.comment.strip():
        raise HTTPException(400, "退回或拒绝时必须填写复核意见")

    task = db.execute(
        select(ReviewTask).where(
            ReviewTask.contract_id == contract_id,
            ReviewTask.status != "completed",
        ).order_by(ReviewTask.id.desc())
    ).scalars().first()
    if task is None:
        task = ReviewTask(contract_id=contract_id, created_by=contract.uploaded_by)
        db.add(task)
        db.flush()
    task.reviewer_id = user.id
    task.status = "completed"
    task.decision = payload.decision
    task.comment = payload.comment.strip()
    task.completed_at = datetime.now()

    contract.status = {"approve": "approved", "reject": "rejected", "changes": "needs_changes"}[payload.decision]
    log(db, user.id, "contract.review", "contract", contract.id, f"{payload.decision}:{payload.comment}")
    db.commit()
    return _detail(db, contract, user)


@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rules = db.execute(select(Rule).order_by(Rule.id)).scalars().all()
    return [
        {
            "id": rule.id,
            "code": rule.code,
            "name": rule.name,
            "category": rule.category,
            "severity": rule.severity,
            "kind": rule.kind,
            "params": json.loads(rule.params or "{}"),
            "message": rule.message,
            "legal_basis": rule.legal_basis,
            "enabled": rule.enabled,
        }
        for rule in rules
    ]


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, payload: dict, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    if "enabled" in payload:
        rule.enabled = bool(payload["enabled"])
    if "severity" in payload and payload["severity"] in ("high", "medium", "low"):
        rule.severity = payload["severity"]
    if "message" in payload:
        rule.message = str(payload["message"])
    log(db, admin.id, "rule.update", "rule", rule.id, json.dumps(payload, ensure_ascii=False))
    db.commit()
    return {"ok": True}


@router.post("/rules")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.execute(select(Rule).where(Rule.code == payload.code)).scalar_one_or_none():
        raise HTTPException(400, "规则代码已存在")
    data = payload.model_dump()
    rule = Rule(**{**data, "params": json.dumps(payload.params, ensure_ascii=False)})
    db.add(rule)
    log(db, admin.id, "rule.create", "rule", payload.code, payload.name)
    db.commit()
    return {"id": rule.id}
