import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, formatAmount, RISK_STATUS_LABEL, SEVERITY_LABEL, STATUS_LABEL } from "../api";
import type { ContractDetail as Detail, Risk } from "../types";

function RiskItem({
  risk,
  contractId,
  canReview,
  onSaved,
}: {
  risk: Risk;
  contractId: number;
  canReview: boolean;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(risk.status);
  const [note, setNote] = useState(risk.note);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await api.patch(`/api/contracts/${contractId}/risks/${risk.id}`, { status, note });
      setEditing(false);
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`risk-item ${risk.severity} ${risk.status !== "open" ? "resolved" : ""}`}>
      <div className="risk-head">
        <div className="risk-title">
          <span className={`severity ${risk.severity}`}>{SEVERITY_LABEL[risk.severity]}</span>
          <strong>{risk.name}</strong>
          <code>{risk.rule_code}</code>
        </div>
        <span className={`risk-status ${risk.status}`}>{RISK_STATUS_LABEL[risk.status]}</span>
      </div>
      <p className="risk-message">{risk.message}</p>
      {risk.evidence && <blockquote>{risk.evidence}</blockquote>}
      {risk.note && !editing && <div className="risk-note">处置说明：{risk.note}</div>}

      {canReview && (
        <div className="risk-actions">
          {editing ? (
            <>
              <select value={status} onChange={(event) => setStatus(event.target.value as Risk["status"])}>
                <option value="open">待处理</option>
                <option value="accepted">接受风险（附条件通过）</option>
                <option value="fixed">已整改</option>
                <option value="ignored">误报忽略</option>
              </select>
              <input
                placeholder="填写处置说明，作为复核记录留痕"
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <button className="btn primary tiny" onClick={save} disabled={busy}>
                {busy ? "保存中…" : "保存"}
              </button>
              <button className="btn ghost tiny" onClick={() => setEditing(false)}>取消</button>
            </>
          ) : (
            <button className="btn ghost tiny" onClick={() => setEditing(true)}>
              处置此项
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function ContractDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<"risks" | "clauses" | "history">("risks");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await api.get<Detail>(`/api/contracts/${id}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载合同失败");
    }
  };

  useEffect(() => {
    load();
  }, [id]);

  if (error) {
    return (
      <div className="page">
        <div className="alert error">{error}</div>
        <button className="btn" onClick={() => navigate("/contracts")}>返回列表</button>
      </div>
    );
  }
  if (!detail) return <div className="muted">加载中…</div>;

  const openHigh = detail.risks.filter((risk) => risk.severity === "high" && risk.status === "open").length;
  const openTotal = detail.risks.filter((risk) => risk.status === "open").length;
  const reviewable = detail.can_review && ["pending_review", "needs_changes"].includes(detail.status);

  const submitReview = async (decision: "approve" | "reject" | "changes") => {
    if (decision !== "approve" && !comment.trim()) {
      setError("退回或拒绝时必须填写复核意见");
      return;
    }
    if (decision === "approve" && openHigh > 0) {
      setError(`仍有 ${openHigh} 项高风险未处置，请先逐项处置后再通过`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api.post<Detail>(`/api/contracts/${detail.id}/review`, { decision, comment });
      setDetail(updated);
      setComment("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page contract-detail">
      <div className="detail-top">
        <Link to="/contracts" className="back-link">← 返回合同列表</Link>
        <div className="detail-actions">
          <button className="btn" onClick={load}>刷新</button>
        </div>
      </div>

      <div className="detail-hero panel">
        <div className="detail-main">
          <div className="detail-eyebrow">
            合同审查 · {detail.filename}
          </div>
          <h2>{detail.title}</h2>
          <div className="detail-meta">
            <span>{detail.counterparty || "未识别对方主体"}</span>
            <span>{formatAmount(detail.amount)}</span>
            <span>{detail.contract_no || "无合同编号"}</span>
            <span>上传人 {detail.uploaded_by || "—"}</span>
          </div>
          <p className="detail-summary">{detail.summary}</p>
        </div>
        <div className="detail-score">
          <div className={`score-big ${detail.risk_level}`}>
            <strong>{detail.risk_score}</strong>
            <span>风险分</span>
          </div>
          <span className={`status ${detail.status}`}>{STATUS_LABEL[detail.status] ?? detail.status}</span>
        </div>
      </div>

      {error && <div className="alert error">{error}</div>}

      <div className="detail-grid">
        <div className="panel">
          <div className="tabs">
            <button className={tab === "risks" ? "on" : ""} onClick={() => setTab("risks")}>
              风险项 <em>{detail.risks.length}</em>
            </button>
            <button className={tab === "clauses" ? "on" : ""} onClick={() => setTab("clauses")}>
              条款抽取 <em>{detail.clauses.length}</em>
            </button>
            <button className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>
              复核记录 <em>{detail.tasks.length}</em>
            </button>
          </div>

          {tab === "risks" && (
            <div className="risk-list">
              {detail.risks.length === 0 && <div className="empty-state">规则引擎未发现风险</div>}
              {detail.risks.map((risk) => (
                <RiskItem
                  key={risk.id}
                  risk={risk}
                  contractId={detail.id}
                  canReview={detail.can_review}
                  onSaved={load}
                />
              ))}
            </div>
          )}

          {tab === "clauses" && (
            <div className="clause-list">
              {detail.clauses.map((clause) => (
                <div key={clause.id} className="clause-item">
                  <div className="clause-head">
                    <strong>{clause.clause_name}</strong>
                    <span className="tag neutral">{clause.clause_type}</span>
                    <span className="muted small">
                      置信度 {(clause.confidence * 100).toFixed(0)}% · {clause.extractor === "llm" ? "模型抽取" : "规则抽取"}
                    </span>
                  </div>
                  <p className="clause-content">{clause.content}</p>
                </div>
              ))}
            </div>
          )}

          {tab === "history" && (
            <div className="history-list">
              {detail.tasks.map((task) => (
                <div key={task.id} className="history-item">
                  <div className="history-dot" />
                  <div>
                    <strong>
                      {task.status === "completed"
                        ? { approve: "复核通过", reject: "复核拒绝", changes: "退回修改" }[task.decision] ?? "已复核"
                        : "待复核"}
                    </strong>
                    <p>{task.comment || "暂无复核意见"}</p>
                    <em>{task.completed_at ? new Date(task.completed_at).toLocaleString("zh-CN") : new Date(task.created_at).toLocaleString("zh-CN")}</em>
                  </div>
                </div>
              ))}
              {detail.tasks.length === 0 && <div className="empty-state">暂无复核记录</div>}
            </div>
          )}
        </div>

        <aside className="panel review-panel">
          <h3>人工复核</h3>
          <p className="muted small">
            规则引擎仅做初筛，合同须由法务确认风险处置后方可出具意见。
          </p>
          <div className="review-facts">
            <div>
              <span>待处理风险</span>
              <strong>{openTotal}</strong>
            </div>
            <div>
              <span>其中高风险</span>
              <strong className={openHigh ? "text-danger" : ""}>{openHigh}</strong>
            </div>
            <div>
              <span>已抽取条款</span>
              <strong>{detail.clauses.length}</strong>
            </div>
          </div>

          {reviewable ? (
            <>
              <label className="field">
                <span>复核意见</span>
                <textarea
                  rows={4}
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="例如：已与业务确认账期 90 天，需补充验收标准后重新提交。"
                />
              </label>
              <div className="review-actions">
                <button className="btn primary block" disabled={busy} onClick={() => submitReview("approve")}>
                  复核通过
                </button>
                <div className="split">
                  <button className="btn" disabled={busy} onClick={() => submitReview("changes")}>
                    退回修改
                  </button>
                  <button className="btn danger" disabled={busy} onClick={() => submitReview("reject")}>
                    拒绝
                  </button>
                </div>
              </div>
              {openHigh > 0 && (
                <div className="hint warn">存在 {openHigh} 项高风险未处置，需逐项处置后才能通过。</div>
              )}
            </>
          ) : (
            <div className="review-done">
              {STATUS_LABEL[detail.status] ?? detail.status}
              <span>
                {detail.can_review ? "当前状态不可复核" : "仅法务或管理员可执行复核"}
              </span>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
