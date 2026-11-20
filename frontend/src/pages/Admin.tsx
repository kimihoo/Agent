import { useEffect, useState } from "react";
import { api, ROLE_LABEL, SEVERITY_LABEL } from "../api";
import Modal from "../components/Modal";
import type { AdminUser, AuditItem, Rule, SystemStatus } from "../types";

const TABS = [
  { value: "users", label: "用户与权限" },
  { value: "rules", label: "审核规则" },
  { value: "audit", label: "操作审计" },
] as const;

export default function Admin() {
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("users");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [logs, setLogs] = useState<AuditItem[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    username: "",
    password: "",
    display_name: "",
    department: "综合部",
    role: "employee",
  });

  const load = async () => {
    try {
      const [u, r, l, s] = await Promise.all([
        api.get<AdminUser[]>("/api/users"),
        api.get<Rule[]>("/api/rules"),
        api.get<AuditItem[]>("/api/audit-logs"),
        api.get<SystemStatus>("/api/system/status"),
      ]);
      setUsers(u);
      setRules(r);
      setLogs(l);
      setStatus(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const patchUser = async (id: number, payload: Record<string, unknown>) => {
    try {
      await api.patch(`/api/users/${id}`, payload);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
    }
  };

  const createUser = async () => {
    try {
      await api.post("/api/users", form);
      setOpen(false);
      setForm({ username: "", password: "", display_name: "", department: "综合部", role: "employee" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  };

  const toggleRule = async (rule: Rule) => {
    await api.patch(`/api/rules/${rule.id}`, { enabled: !rule.enabled });
    await load();
  };

  return (
    <div className="page">
      <div className="stat-row">
        <div className="stat-card"><span>用户</span><strong>{status?.stats.users ?? "—"}</strong></div>
        <div className="stat-card"><span>知识库</span><strong>{status?.stats.knowledge_bases ?? "—"}</strong></div>
        <div className="stat-card"><span>索引切片</span><strong>{status?.stats.chunks ?? "—"}</strong></div>
        <div className="stat-card"><span>待复核合同</span><strong>{status?.stats.contracts_pending ?? "—"}</strong></div>
      </div>

      <div className="mode-banner">
        <div>
          <span className={`dot ${status?.llm_enabled ? "ok" : "local"}`} />
          <strong>{status?.llm_enabled ? "已接入 OpenAI 兼容大模型" : "当前为本地检索模式"}</strong>
          <p>
            {status?.llm_enabled
              ? `LLM：${status.llm}；Embedding：${status.embedding}`
              : "未配置 LLM_BASE_URL / LLM_API_KEY，回答由检索结果抽取整理。配置环境变量后重启即可启用大模型与语义向量。"}
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <div className="tabs inline">
            {TABS.map((item) => (
              <button key={item.value} className={tab === item.value ? "on" : ""} onClick={() => setTab(item.value)}>
                {item.label}
              </button>
            ))}
          </div>
          {tab === "users" && <button className="btn primary" onClick={() => setOpen(true)}>新增用户</button>}
        </div>

        {error && <div className="alert error">{error}</div>}

        {tab === "users" && (
          <table className="table">
            <thead>
              <tr><th>用户</th><th>部门</th><th>角色</th><th>状态</th><th>创建时间</th></tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="doc-title">{user.display_name}</div>
                    <div className="muted small">@{user.username}</div>
                  </td>
                  <td>
                    <input
                      className="inline-input"
                      defaultValue={user.department}
                      onBlur={(event) => {
                        if (event.target.value !== user.department) patchUser(user.id, { department: event.target.value });
                      }}
                    />
                  </td>
                  <td>
                    <select
                      value={user.role}
                      onChange={(event) => patchUser(user.id, { role: event.target.value })}
                    >
                      {Object.entries(ROLE_LABEL).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button
                      className={`switch ${user.is_active ? "on" : ""}`}
                      onClick={() => patchUser(user.id, { is_active: !user.is_active })}
                    >
                      <span />
                      {user.is_active ? "启用" : "停用"}
                    </button>
                  </td>
                  <td className="muted small">{new Date(user.created_at).toLocaleDateString("zh-CN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "rules" && (
          <table className="table">
            <thead>
              <tr><th>规则</th><th>分类</th><th>等级</th><th>类型</th><th>规则说明</th><th>启用</th></tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <div className="doc-title">{rule.name}</div>
                    <div className="muted small">{rule.code}</div>
                  </td>
                  <td>{rule.category}</td>
                  <td><span className={`severity ${rule.severity}`}>{SEVERITY_LABEL[rule.severity]}</span></td>
                  <td><code>{rule.kind}</code></td>
                  <td className="small">{rule.message}</td>
                  <td>
                    <button className={`switch ${rule.enabled ? "on" : ""}`} onClick={() => toggleRule(rule)}>
                      <span />
                      {rule.enabled ? "启用" : "停用"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "audit" && (
          <table className="table">
            <thead>
              <tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>详情</th></tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="muted small">{new Date(log.created_at).toLocaleString("zh-CN")}</td>
                  <td>{log.actor}</td>
                  <td><code>{log.action}</code></td>
                  <td className="small">{log.target_type} {log.target_id}</td>
                  <td className="small">{log.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {open && (
        <Modal
          title="新增用户"
          subtitle="角色决定知识库可见范围与合同复核权限"
          onClose={() => setOpen(false)}
          footer={
            <>
              <button className="btn" onClick={() => setOpen(false)}>取消</button>
              <button className="btn primary" onClick={createUser}>创建</button>
            </>
          }
        >
          <div className="field-row">
            <label className="field">
              <span>登录账号</span>
              <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </label>
            <label className="field">
              <span>初始密码</span>
              <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </label>
          </div>
          <label className="field">
            <span>姓名</span>
            <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          </label>
          <div className="field-row">
            <label className="field">
              <span>部门</span>
              <input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            </label>
            <label className="field">
              <span>角色</span>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {Object.entries(ROLE_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          </div>
        </Modal>
      )}
    </div>
  );
}
