"""合同结构化抽取与规则校验。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import LLM_ENABLED
from ..models import Contract, ContractClause, ContractRisk, Rule

CLAUSE_TYPES: dict[str, dict] = {
    "party": {"name": "合同主体", "keywords": ["甲方", "乙方", "委托方", "受托方", "法定代表人"]},
    "subject": {"name": "标的与服务范围", "keywords": ["服务内容", "服务范围", "标的", "工作内容", "项目内容", "采购内容"]},
    "payment": {"name": "价款与支付", "keywords": ["价款", "报酬", "服务费", "合同金额", "支付", "付款", "结算", "发票"]},
    "term": {"name": "履行期限", "keywords": ["期限", "有效期", "履行期", "服务期", "合作期"]},
    "liability": {"name": "违约责任", "keywords": ["违约", "赔偿", "滞纳金", "损失"]},
    "confidentiality": {"name": "保密条款", "keywords": ["保密", "商业秘密", "机密"]},
    "dispute": {"name": "争议解决", "keywords": ["争议", "仲裁", "诉讼", "管辖", "法院"]},
    "acceptance": {"name": "验收标准", "keywords": ["验收", "交付标准", "合格", "交付物"]},
    "ip": {"name": "知识产权", "keywords": ["知识产权", "著作权", "专利", "商标", "成果归属"]},
    "termination": {"name": "合同解除", "keywords": ["解除", "终止", "提前终止"]},
}

SEVERITY_WEIGHT = {"high": 30, "medium": 15, "low": 5}

HEADING_RE = re.compile(
    r"(?m)^\s*(?:第[一二三四五六七八九十百零〇\d]+条[^\n]{0,40}"
    r"|[一二三四五六七八九十]+、[^\n]{0,40}"
    r"|\d+(?:\.\d+){0,2}[、.．]\s*[^\n]{0,40}"
    r"|#{1,4}\s+[^\n]{0,40})\s*$"
)


@dataclass
class Segment:
    heading: str
    content: str
    start: int
    end: int
    page: int = 1


def _segments(text: str) -> list[Segment]:
    matches = list(HEADING_RE.finditer(text))
    segments: list[Segment] = []
    if not matches:
        return [Segment("正文", text, 0, len(text))]
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            segments.append(Segment("首部", preamble, 0, matches[0].start()))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        heading = match.group(0).strip()
        body = text[match.end() : end].strip()
        segments.append(Segment(heading, body, match.start(), end))
    return segments


def _classify(segment: Segment, is_preamble: bool) -> list[tuple[str, int]]:
    heading = segment.heading
    body = segment.content
    scored: list[tuple[str, int, int]] = []
    for clause_type, meta in CLAUSE_TYPES.items():
        if is_preamble and clause_type != "party":
            continue
        if not is_preamble and clause_type == "party" and not re.search(r"主体|当事人|甲方|乙方", heading):
            continue
        heading_hits = sum(heading.count(keyword) for keyword in meta["keywords"])
        body_hits = sum(body.count(keyword) for keyword in meta["keywords"])
        if is_preamble:
            if heading_hits or body_hits:
                scored.append((clause_type, heading_hits * 3 + body_hits, heading_hits))
            continue
        if heading_hits or body_hits >= 2:
            scored.append((clause_type, heading_hits * 4 + body_hits, heading_hits))
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        return []
    result = [(scored[0][0], scored[0][1])]
    for clause_type, score, heading_hits in scored[1:]:
        if heading_hits and score >= 4:
            result.append((clause_type, score))
            break
    return result


def extract_clauses(text: str) -> list[dict]:
    """按条款标题切分并按关键词归类，同一类型合并为结构化条款。"""
    buckets: dict[str, dict] = {}
    segments = _segments(text)
    for index, segment in enumerate(segments):
        is_preamble = index == 0 and segment.heading in ("首部", "正文")
        for clause_type, hits in _classify(segment, is_preamble):
            bucket = buckets.setdefault(
                clause_type,
                {"content": "", "headings": [], "start": segment.start, "end": segment.end, "hits": 0},
            )
            if bucket["content"]:
                bucket["content"] += "\n"
            bucket["content"] += f"{segment.heading}\n{segment.content}" if segment.heading != "正文" else segment.content
            bucket["headings"].append(segment.heading)
            bucket["start"] = min(bucket["start"], segment.start)
            bucket["end"] = max(bucket["end"], segment.end)
            bucket["hits"] += hits

    # 兜底：正文中同时出现甲乙双方但未识别出主体条款
    if "party" not in buckets and "甲方" in text and "乙方" in text:
        match = re.search(r"甲\s*方[^\n]{0,80}?乙\s*方[^\n]{0,120}", text, re.S)
        if match:
            buckets["party"] = {
                "content": match.group(0),
                "headings": ["合同主体"],
                "start": match.start(),
                "end": match.end(),
                "hits": 2,
            }

    clauses: list[dict] = []
    for clause_type, bucket in buckets.items():
        content = bucket["content"].strip()
        if not content:
            continue
        clauses.append(
            {
                "clause_type": clause_type,
                "heading": bucket["headings"][0] if bucket["headings"] else CLAUSE_TYPES[clause_type]["name"],
                "content": content[:2000],
                "start_char": bucket["start"],
                "end_char": bucket["end"],
                "page": 1,
                "confidence": min(0.95, 0.55 + 0.08 * bucket["hits"]),
                "extractor": "rule",
            }
        )
    return clauses


_NUM = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"


def _to_amount(value: str, unit: str) -> float:
    number = float(value.replace(",", ""))
    return number * 10000 if unit == "万元" else number


def extract_fields(text: str) -> dict:
    fields: dict = {}

    amount_match = re.search(
        rf"(?:合同总金额|合同金额|总金额|总价款|服务费总额|价款合计)[^\n。；]{{0,25}}?(?:人民币)?\s*[¥￥]?\s*{_NUM}\s*(万元|元)", text
    )
    if amount_match:
        fields["amount"] = _to_amount(amount_match.group(1), amount_match.group(2))

    days = []
    for pattern in (
        r"(?:付款|支付)[^\n。；]{0,20}?(\d{1,3})\s*(?:个)?(?:工作)?日(?:内|以内|之内)",
        r"(\d{1,3})\s*(?:个)?(?:工作)?日(?:内|以内|之内)[^\n。；]{0,12}?(?:支付|付款)",
        r"账期[^\n。；]{0,12}?(\d{1,3})\s*(?:天|日)",
    ):
        days.extend(int(value) for value in re.findall(pattern, text))
    if days:
        fields["payment_days"] = max(days)

    ratio_patterns = {
        "penalty_ratio": (
            r"违约金[^\n。；]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"([0-9]+(?:\.[0-9]+)?)\s*%[^\n。；]{0,10}?违约金",
        ),
        "prepay_ratio": (
            r"预付(?:款|费用|比例)?[^\n。；]{0,25}?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"([0-9]+(?:\.[0-9]+)?)\s*%[^\n。；]{0,8}?预付",
        ),
    }
    for field, patterns in ratio_patterns.items():
        values: list[float] = []
        for pattern in patterns:
            values.extend(float(value) for value in re.findall(pattern, text))
        if values:
            fields[field] = max(values)

    no_match = re.search(r"合同编号[：:\s]*([A-Za-z0-9\u4e00-\u9fff\-_/〔〕（）()]+)", text)
    if no_match:
        fields["contract_no"] = no_match.group(1).strip()

    for side in ("甲方", "乙方"):
        match = re.search(rf"{side}(?:（[^）]*）)?[：:]\s*([^\n]{{2,60}})", text)
        if match:
            fields[side] = re.sub(r"\s{2,}.*$", "", match.group(1)).strip()

    date_match = re.search(r"(?:签订|签署)日期[：:\s]*([0-9]{4}[年\-/][0-9]{1,2}[月\-/][0-9]{1,2}日?)", text)
    if date_match:
        fields["sign_date"] = date_match.group(1)

    return fields


CONTRACT_JSON_SCHEMA = """请从合同文本中抽取结构化信息，仅输出 JSON，不要解释：
{
  "contract_no": "合同编号或空字符串",
  "counterparty": "对方单位名称或空字符串",
  "amount": 合同金额数字（元）或 null,
  "payment_days": 付款账期天数或 null,
  "penalty_ratio": 违约金比例（%）或 null,
  "prepay_ratio": 预付比例（%）或 null,
  "clauses": [{"clause_type": "party|subject|payment|term|liability|confidentiality|dispute|acceptance|ip|termination", "heading": "标题", "content": "条款原文"}]
}"""


def llm_extract(text: str) -> dict | None:
    """可选：调用大模型做语义抽取；失败时返回 None 由规则结果兜底。"""
    if not LLM_ENABLED:
        return None
    from .llm import chat_completion

    try:
        raw = chat_completion(
            [
                {"role": "system", "content": "你是企业合同条款抽取引擎，严格按 JSON 输出。"},
                {"role": "user", "content": f"{CONTRACT_JSON_SCHEMA}\n\n合同文本：\n{text[:12000]}"},
            ]
        )
        match = re.search(r"\{.*\}", raw, re.S)
        return json.loads(match.group(0)) if match else None
    except Exception:  # noqa: BLE001
        return None


def _snippet(text: str, keyword: str, radius: int = 70) -> str:
    index = text.find(keyword)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(keyword) + radius)
    return text[start:end].replace("\n", " ").strip()


def evaluate_rules(
    db: Session, text: str, clauses: dict[str, str], fields: dict, contract: Contract
) -> list[ContractRisk]:
    rules = db.query(Rule).filter(Rule.enabled.is_(True)).order_by(Rule.id).all()
    risks: list[ContractRisk] = []

    def add(rule: Rule, message: str, evidence: str, clause_type: str = "") -> None:
        risks.append(
            ContractRisk(
                contract_id=contract.id,
                rule_code=rule.code,
                name=rule.name,
                severity=rule.severity,
                message=message,
                evidence=evidence,
                clause_type=clause_type,
                page=1,
            )
        )

    for rule in rules:
        params = json.loads(rule.params or "{}")
        kind = rule.kind
        if kind == "required_clause":
            clause_type = params.get("clause_type", "")
            if clause_type not in clauses:
                add(rule, rule.message or f"未找到「{CLAUSE_TYPES.get(clause_type, {}).get('name', clause_type)}」相关条款",
                    "合同全文中未检索到对应条款", clause_type)
        elif kind == "keyword_any":
            clause_type = params.get("clause_type", "")
            pool = clauses.get(clause_type, text) if clause_type else text
            if not any(keyword in pool for keyword in params.get("keywords", [])):
                add(rule, rule.message, _snippet(pool, "争议") or "相关条款未见明确约定", clause_type)
        elif kind == "keyword_none":
            for keyword in params.get("keywords", []):
                if keyword in text:
                    add(rule, rule.message, _snippet(text, keyword))
                    break
        elif kind in ("max_number", "min_number"):
            field = params.get("field", "")
            value = fields.get(field)
            if value is None:
                continue
            limit = params.get("limit", 0)
            if kind == "max_number" and value > limit:
                add(rule, rule.message.format(value=value, limit=limit),
                    f"{_FIELD_LABEL.get(field, field)}：{value:g}")
            if kind == "min_number" and value < limit:
                add(rule, rule.message.format(value=value, limit=limit),
                    f"{_FIELD_LABEL.get(field, field)}：{value:g}")
        elif kind == "clause_keyword_none":
            clause_type = params.get("clause_type", "")
            pool = clauses.get(clause_type, "")
            for keyword in params.get("keywords", []):
                if keyword in pool:
                    add(rule, rule.message, _snippet(pool, keyword), clause_type)
                    break

    return risks


_FIELD_LABEL = {
    "payment_days": "付款账期（天）",
    "penalty_ratio": "违约金比例（%）",
    "prepay_ratio": "预付比例（%）",
}


def risk_score(risks: list[ContractRisk]) -> tuple[int, str]:
    if not risks:
        return 0, "low"
    score = min(100, sum(SEVERITY_WEIGHT.get(risk.severity, 5) for risk in risks))
    severities = {risk.severity for risk in risks}
    if "high" in severities:
        level = "high"
    elif "medium" in severities or score >= 30:
        level = "medium"
    else:
        level = "low"
    return score, level


def summarize(contract: Contract, risks: list[ContractRisk], clauses: list[ContractClause]) -> str:
    high = sum(1 for risk in risks if risk.severity == "high")
    medium = sum(1 for risk in risks if risk.severity == "medium")
    low = sum(1 for risk in risks if risk.severity == "low")
    parts = [
        f"共抽取 {len(clauses)} 类结构化条款，命中 {len(risks)} 项规则风险"
        f"（高 {high} / 中 {medium} / 低 {low}）。"
    ]
    if high:
        parts.append("高优先级问题：" + "；".join(risk.name for risk in risks if risk.severity == "high") + "。")
    parts.append("以上为规则引擎初筛结果，须由法务人员人工复核后方可出具意见。")
    return "".join(parts)


def apply_llm_fields(fields: dict, payload: dict | None) -> dict:
    if not payload:
        return fields
    merged = dict(fields)
    for key in ("contract_no", "counterparty", "amount", "payment_days", "penalty_ratio", "prepay_ratio"):
        value = payload.get(key)
        if value not in (None, "", 0):
            merged[key] = value
    return merged
