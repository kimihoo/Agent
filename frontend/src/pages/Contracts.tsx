import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatAmount, STATUS_LABEL } from "../api";
import Modal from "../components/Modal";
import type { ContractListItem } from "../types";

const FILTERS = [
  { value: "all", label: "全部" },
  { value: "pending_review", label: "待复核" },
  { value: "needs_changes", label: "待修改" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已拒绝" },
];

export default function Contracts() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ContractListItem[]>([]);
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () =>
    api.get<ContractListItem[]>("/api/contracts").then(setItems).catch((err: Error) => setError(err.message));

  useEffect(() => {
    load();
  }, []);

  const stats = useMemo(() => {
    const pending = items.filter((item) => item.status === "pending_review" || item.status === "needs_changes").length;
    const high = items.filter((item) => item.risk_level === "high").length;
    const approved = items.filter((item) => item.status === "approved").length;
    return { pending, high, approved, total: items.length };
  }, [items]);

  const filtered = filter === "all" ? items : items.filter((item) => item.status === filter);

  const upload = async () => {
    if (!file) {
      setError("请选择合同文件");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api.upload<{ id: number }>("/api/contracts", file, title);
      setOpen(false);
      setFile(null);
      setTitle("");
      await load();
      navigate(`/contracts/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="stat-row">
        <div className="stat-card">
          <span>合同总数</span>
          <strong>{stats.total}</strong>
        </div>
        <div className="stat-card accent">
          <span>待复核</span>
          <strong>{stats.pending}</strong>
        </div>
        <div className="stat-card danger">
          <span>高风险合同</span>
          <strong>{stats.high}</strong>
        </div>
        <div className="stat-card ok">
          <span>已通过</span>
          <strong>{stats.approved}</strong>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>合同审查列表</h2>
            <p>上传后自动完成条款抽取与规则初筛，法务确认风险处置后方可通过</p>
          </div>
          <div className="row-actions">
            <div className="segmented">
              {FILTERS.map((item) => (
                <button
                  key={item.value}
                  className={filter === item.value ? "on" : ""}
                  onClick={() => setFilter(item.value)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button className="btn primary" onClick={() => setOpen(true)}>上传合同</button>
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}

        <div className="contract-list">
          {filtered.map((item) => (
            <button key={item.id} className="contract-row" onClick={() => navigate(`/contracts/${item.id}`)}>
              <div className="contract-main">
                <div className="contract-title">
                  {item.title}
                  <span className={`status ${item.status}`}>{STATUS_LABEL[item.status] ?? item.status}</span>
                </div>
                <div className="contract-sub">
                  {item.counterparty || "未识别对方主体"} · {formatAmount(item.amount)} ·{" "}
                  {new Date(item.created_at).toLocaleDateString("zh-CN")}
                </div>
              </div>
              <div className="risk-counts">
                <span className="risk-pill high">高 {item.risk_counts.high ?? 0}</span>
                <span className="risk-pill medium">中 {item.risk_counts.medium ?? 0}</span>
                <span className="risk-pill low">低 {item.risk_counts.low ?? 0}</span>
              </div>
              <div className={`score-ring ${item.risk_level}`}>
                <strong>{item.risk_score}</strong>
                <em>风险分</em>
              </div>
            </button>
          ))}
          {filtered.length === 0 && <div className="empty-state">暂无合同，点击右上角上传</div>}
        </div>
      </div>

      {open && (
        <Modal
          title="上传合同"
          subtitle="支持 PDF / DOCX / TXT / Markdown，单文件不超过 25MB"
          onClose={() => setOpen(false)}
          footer={
            <>
              <button className="btn" onClick={() => setOpen(false)}>取消</button>
              <button className="btn primary" onClick={upload} disabled={busy}>
                {busy ? "解析与校验中…" : "上传并分析"}
              </button>
            </>
          }
        >
          <label className="upload-zone">
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,.markdown"
              hidden
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <strong>{file ? file.name : "点击选择合同文件"}</strong>
            <span>系统将抽取合同主体、金额、付款、违约、保密、争议解决等条款</span>
          </label>
          <label className="field">
            <span>合同名称（可选）</span>
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="默认使用文件名" />
          </label>
          {error && <div className="alert error">{error}</div>}
        </Modal>
      )}
    </div>
  );
}
