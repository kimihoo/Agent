import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const DEMO = [
  { username: "emp", password: "emp123", label: "普通员工", desc: "市场部 · 4 个知识库" },
  { username: "legal", password: "legal123", label: "法务专员", desc: "合同复核 · 5 个知识库" },
  { username: "fin", password: "fin123", label: "财务专员", desc: "报销制度 · 受限库只读" },
  { username: "admin", password: "admin123", label: "系统管理员", desc: "全部权限与系统配置" },
];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("emp");
  const [password, setPassword] = useState("emp123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      const from = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <section className="login-hero">
        <div className="hero-glow" />
        <div className="hero-brand">
          <div className="hero-logo">星</div>
          <span>星云知识引擎</span>
        </div>
        <h2>让企业知识<br />可问、可查、可追溯</h2>
        <p className="hero-desc">
          统一接入制度、系统手册与合同规范。员工用自然语言提问，答案自动附带原文出处；
          合同审查采用结构化抽取与规则校验，并由法务人工复核兜底。
        </p>
        <ul className="hero-points">
          <li><span>01</span>员工制度 / 系统操作 / 运营资料问答</li>
          <li><span>02</span>按部门与角色隔离的知识库权限</li>
          <li><span>03</span>合同条款抽取、规则风控与复核闭环</li>
        </ul>
        <div className="hero-foot">内部系统 · 数据不出企业 · 支持本地模型</div>
      </section>

      <section className="login-panel">
        <form className="login-card" onSubmit={submit}>
          <h3>登录工作台</h3>
          <p className="muted">使用企业账号登录，系统将按你的部门与角色加载可用知识库。</p>

          <label className="field">
            <span>账号</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>

          {error && <div className="alert error">{error}</div>}

          <button className="btn primary block" disabled={busy}>
            {busy ? "登录中…" : "登录"}
          </button>

          <div className="demo-block">
            <div className="demo-title">演示账号（点击填充）</div>
            <div className="demo-grid">
              {DEMO.map((item) => (
                <button
                  type="button"
                  key={item.username}
                  className="demo-item"
                  onClick={() => {
                    setUsername(item.username);
                    setPassword(item.password);
                  }}
                >
                  <strong>{item.label}</strong>
                  <span>{item.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}
