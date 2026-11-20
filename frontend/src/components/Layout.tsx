import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, ROLE_LABEL } from "../api";
import { useAuth } from "../auth";
import type { SystemStatus } from "../types";

function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    chat: <path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.3 8.9 8.9 0 0 1-3.6-.8L4 20l1.2-3.6A8.2 8.2 0 0 1 3.9 11.5 8.4 8.4 0 0 1 12.4 3 8.4 8.4 0 0 1 21 11.5Z" />,
    book: <><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17.5H6.5A2.5 2.5 0 0 0 4 22V4.5Z" /><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /><path d="M8 13h8M8 17h5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z" /></>,
    spark: <><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="m5.6 5.6 2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" /></>,
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "智能问答", subtitle: "基于企业制度与业务资料，给出可溯源的回答" },
  "/knowledge": { title: "知识库", subtitle: "管理文档、切片索引与访问权限" },
  "/contracts": { title: "合同审查", subtitle: "结构化条款抽取 + 规则校验 + 法务人工复核" },
  "/admin": { title: "系统管理", subtitle: "用户权限、审核规则与操作审计" },
};

export default function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    api.get<SystemStatus>("/api/system/status").then(setStatus).catch(() => undefined);
  }, []);

  const base = location.pathname.startsWith("/contracts") ? "/contracts" : location.pathname;
  const meta = TITLES[base] ?? TITLES["/"];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Icon name="spark" />
          </div>
          <div>
            <div className="brand-name">星云知识引擎</div>
            <div className="brand-sub">Enterprise AI KB</div>
          </div>
        </div>

        <nav className="nav">
          <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon name="chat" />
            <span>智能问答</span>
          </NavLink>
          <NavLink to="/knowledge" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon name="book" />
            <span>知识库</span>
          </NavLink>
          <NavLink to="/contracts" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon name="file" />
            <span>合同审查</span>
          </NavLink>
          {user?.role === "admin" && (
            <NavLink to="/admin" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              <Icon name="settings" />
              <span>系统管理</span>
            </NavLink>
          )}
        </nav>

        <div className="sidebar-foot">
          <div className="model-badge" title={status ? `LLM: ${status.llm}｜Embedding: ${status.embedding}` : ""}>
            <span className={`dot ${status?.llm_enabled ? "ok" : "local"}`} />
            {status?.llm_enabled ? "大模型已连接" : "本地检索模式"}
          </div>
          <div className="user-card">
            <div className="avatar">{user?.display_name?.[0] ?? "U"}</div>
            <div className="user-meta">
              <div className="user-name">{user?.display_name}</div>
              <div className="user-role">
                {ROLE_LABEL[user?.role ?? ""] ?? user?.role} · {user?.department}
              </div>
            </div>
            <button className="icon-btn" onClick={logout} title="退出登录">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1>{meta.title}</h1>
            <p>{meta.subtitle}</p>
          </div>
          <div className="topbar-right">
            {status && (
              <div className="stat-chips">
                <span className="chip">知识库 {status.stats.knowledge_bases}</span>
                <span className="chip">文档 {status.stats.documents}</span>
                <span className="chip warn">待复核合同 {status.stats.contracts_pending}</span>
              </div>
            )}
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
