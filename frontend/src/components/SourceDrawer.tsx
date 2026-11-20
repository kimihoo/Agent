import { useEffect, useState } from "react";
import { api } from "../api";
import type { Citation } from "../types";

export default function SourceDrawer({
  citation,
  onClose,
}: {
  citation: Citation;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setText("");
    setError("");
    api
      .get<{ text: string; title: string }>(`/api/documents/${citation.doc_id}/text`)
      .then((data) => setText(data.text))
      .catch((err: Error) => setError(err.message));
  }, [citation.doc_id]);

  const start = citation.start_char;
  const end = citation.end_char;
  const windowStart = Math.max(0, start - 320);
  const windowEnd = Math.min(text.length || end + 120, end + 320);
  const before = text.slice(windowStart, start);
  const highlighted = text.slice(start, end);
  const after = text.slice(end, windowEnd);

  return (
    <>
      <div className="drawer-mask" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <div>
            <div className="drawer-eyebrow">原文位置 · 引用 [{citation.index}]</div>
            <h3>{citation.doc_title}</h3>
            <div className="drawer-meta">
              <span>{citation.kb_name}</span>
              <span>第 {citation.page} 页</span>
              {citation.section && <span>{citation.section}</span>}
            </div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="drawer-body">
          {error && <div className="alert error">{error}</div>}
          {!text && !error && <div className="muted">正在加载原文…</div>}
          {text && (
            <div className="source-text">
              {before && <span className="dim">{before}</span>}
              <mark>{highlighted || citation.snippet}</mark>
              {after && <span className="dim">{after}</span>}
            </div>
          )}

          <div className="drawer-card">
            <div className="drawer-card-title">检索切片</div>
            <p>{citation.snippet}</p>
            <div className="drawer-card-foot">相关度 {(citation.score * 100).toFixed(1)}</div>
          </div>
        </div>
      </aside>
    </>
  );
}
