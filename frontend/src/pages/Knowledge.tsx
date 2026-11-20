import { useEffect, useRef, useState } from "react";
import { api, formatBytes } from "../api";
import { useAuth } from "../auth";
import Modal from "../components/Modal";
import type { Doc, KB } from "../types";

const VISIBILITY_LABEL: Record<string, string> = {
  public: "全员公开",
  internal: "公司内部",
  restricted: "受限访问",
};

interface Permission {
  id: number;
  principal_type: string;
  principal: string;
  permission: string;
}

export default function Knowledge() {
  const { user } = useAuth();
  const [kbs, setKbs] = useState<KB[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [permOpen, setPermOpen] = useState(false);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [form, setForm] = useState({ name: "", description: "", department: "综合部", visibility: "internal" });
  const [permForm, setPermForm] = useState({ principal_type: "department", principal: "", permission: "read" });
  const fileRef = useRef<HTMLInputElement>(null);

  const activeKb = kbs.find((kb) => kb.id === activeId) ?? null;
  const canWrite = activeKb?.my_permission === "write";

  const loadKbs = async (keep = activeId) => {
    const list = await api.get<KB[]>("/api/kbs");
    setKbs(list);
    if (list.length && !list.some((kb) => kb.id === keep)) setActiveId(list[0].id);
    else if (keep) setActiveId(keep);
  };

  const loadDocs = async (kbId: number) => {
    try {
      setDocs(await api.get<Doc[]>(`/api/kbs/${kbId}/documents`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载文档失败");
    }
  };

  useEffect(() => {
    loadKbs().catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (activeId) loadDocs(activeId);
    else setDocs([]);
  }, [activeId]);

  const upload = async (file: File) => {
    if (!activeKb) return;
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const doc = await api.upload<Doc>(`/api/kbs/${activeKb.id}/documents`, file);
      if (doc.status === "failed") setError(`《${doc.title}》入库失败：${doc.error}`);
      else setNotice(`《${doc.title}》已解析并建立 ${doc.chunk_count} 个索引切片`);
      await loadDocs(activeKb.id);
      await loadKbs(activeKb.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const removeDoc = async (doc: Doc) => {
    if (!window.confirm(`删除文档《${doc.title}》及其索引？`)) return;
    await api.del(`/api/documents/${doc.id}`);
    await loadDocs(doc.kb_id);
    await loadKbs(doc.kb_id);
  };

  const reindex = async (doc: Doc) => {
    setNotice("");
    const result = await api.post<Doc>(`/api/documents/${doc.id}/reindex`);
    if (result.status === "failed") setError(result.error);
    else setNotice(`《${doc.title}》重建索引完成`);
    await loadDocs(doc.kb_id);
  };

  const createKb = async () => {
    if (!form.name.trim()) return;
    try {
      const result = await api.post<{ id: number }>("/api/kbs", form);
      setCreateOpen(false);
      setForm({ name: "", description: "", department: "综合部", visibility: "internal" });
      await loadKbs(result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建失败");
    }
  };

  const openPermissions = async () => {
    if (!activeKb) return;
    try {
      setPermissions(await api.get<Permission[]>(`/api/kbs/${activeKb.id}/permissions`));
      setPermOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载权限失败");
    }
  };

  const addPermission = async () => {
    if (!activeKb || !permForm.principal.trim()) return;
    try {
      await api.post(`/api/kbs/${activeKb.id}/permissions`, permForm);
      setPermissions(await api.get<Permission[]>(`/api/kbs/${activeKb.id}/permissions`));
      setPermForm({ principal_type: "department", principal: "", permission: "read" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "授权失败");
    }
  };

  const removePermission = async (id: number) => {
    if (!activeKb) return;
    await api.del(`/api/kbs/${activeKb.id}/permissions/${id}`);
    setPermissions(await api.get<Permission[]>(`/api/kbs/${activeKb.id}/permissions`));
  };

  return (
    <div className="kb-layout">
      <aside className="kb-list">
        <div className="panel-head">
          <div>
            <h2>知识库</h2>
            <p>{kbs.length} 个可访问</p>
          </div>
          {user?.role !== "employee" && (
            <button className="btn small" onClick={() => setCreateOpen(true)}>
              新建
            </button>
          )}
        </div>
        {kbs.map((kb) => (
          <button
            key={kb.id}
            className={`kb-card ${activeId === kb.id ? "active" : ""}`}
            onClick={() => setActiveId(kb.id)}
          >
            <div className="kb-card-top">
              <strong>{kb.name}</strong>
              <span className={`tag ${kb.visibility}`}>{VISIBILITY_LABEL[kb.visibility]}</span>
            </div>
            <p>{kb.description}</p>
            <div className="kb-card-foot">
              <span>{kb.department}</span>
              <span>{kb.document_count} 文档 · {kb.chunk_count} 切片</span>
            </div>
          </button>
        ))}
        {kbs.length === 0 && <div className="muted">暂无可访问的知识库</div>}
      </aside>

      <section className="kb-docs panel">
        {activeKb ? (
          <>
            <div className="panel-head">
              <div>
                <h2>{activeKb.name}</h2>
                <p>
                  {activeKb.description} · {activeKb.department} ·{" "}
                  {canWrite ? "可管理" : "只读"}
                </p>
              </div>
              <div className="row-actions">
                <button className="btn small" onClick={openPermissions} disabled={!canWrite}>
                  权限
                </button>
                <button className="btn primary small" onClick={() => fileRef.current?.click()} disabled={!canWrite || uploading}>
                  {uploading ? "解析中…" : "上传文档"}
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.docx,.txt,.md,.markdown"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) upload(file);
                  }}
                />
              </div>
            </div>

            {error && <div className="alert error">{error}</div>}
            {notice && <div className="alert ok">{notice}</div>}

            <table className="table">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>状态</th>
                  <th>大小</th>
                  <th>切片</th>
                  <th>页数</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <div className="doc-title">{doc.title}</div>
                      <div className="muted small">{doc.filename}</div>
                    </td>
                    <td>
                      <span className={`status ${doc.status}`}>
                        {doc.status === "ready" ? "已索引" : doc.status === "failed" ? "失败" : "解析中"}
                      </span>
                      {doc.error && <div className="error-text">{doc.error}</div>}
                    </td>
                    <td>{formatBytes(doc.size)}</td>
                    <td>{doc.chunk_count}</td>
                    <td>{doc.page_count || 1}</td>
                    <td>
                      <div className="row-actions">
                        <button className="btn ghost tiny" onClick={() => reindex(doc)} disabled={!canWrite}>
                          重建索引
                        </button>
                        <button className="btn ghost tiny danger" onClick={() => removeDoc(doc)} disabled={!canWrite}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {docs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty-cell">
                      暂无文档，上传 PDF / DOCX / Markdown 后自动解析切片并向量化
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <div className="hint">
              支持 PDF、DOCX、TXT、Markdown，单文件不超过 25MB。检索时按部门与角色过滤知识库，答案会附带文档名、章节与页码。
            </div>
          </>
        ) : (
          <div className="empty-state">请选择一个知识库</div>
        )}
      </section>

      {createOpen && (
        <Modal
          title="新建知识库"
          subtitle="创建后可通过「权限」按钮向部门、角色或具体用户授权"
          onClose={() => setCreateOpen(false)}
          footer={
            <>
              <button className="btn" onClick={() => setCreateOpen(false)}>取消</button>
              <button className="btn primary" onClick={createKb}>创建</button>
            </>
          }
        >
          <label className="field">
            <span>名称</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如：销售管理制度库" />
          </label>
          <label className="field">
            <span>描述</span>
            <textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <div className="field-row">
            <label className="field">
              <span>归属部门</span>
              <input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            </label>
            <label className="field">
              <span>可见范围</span>
              <select value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value })}>
                <option value="internal">公司内部</option>
                <option value="public">全员公开</option>
                <option value="restricted">受限访问</option>
              </select>
            </label>
          </div>
        </Modal>
      )}

      {permOpen && activeKb && (
        <Modal
          title={`${activeKb.name} · 访问权限`}
          subtitle="受限知识库仅创建人、归属部门成员与显式授权对象可访问"
          onClose={() => setPermOpen(false)}
          wide
        >
          <div className="perm-form">
            <select
              value={permForm.principal_type}
              onChange={(e) => setPermForm({ ...permForm, principal_type: e.target.value })}
            >
              <option value="department">部门</option>
              <option value="role">角色</option>
              <option value="user">用户</option>
            </select>
            <input
              placeholder={permForm.principal_type === "department" ? "如：财务部" : permForm.principal_type === "role" ? "legal / finance / hr" : "登录账号"}
              value={permForm.principal}
              onChange={(e) => setPermForm({ ...permForm, principal: e.target.value })}
            />
            <select value={permForm.permission} onChange={(e) => setPermForm({ ...permForm, permission: e.target.value })}>
              <option value="read">只读</option>
              <option value="write">可管理</option>
            </select>
            <button className="btn primary" onClick={addPermission}>添加</button>
          </div>
          <table className="table">
            <thead>
              <tr><th>类型</th><th>对象</th><th>权限</th><th></th></tr>
            </thead>
            <tbody>
              {permissions.map((perm) => (
                <tr key={perm.id}>
                  <td>{{ department: "部门", role: "角色", user: "用户" }[perm.principal_type] ?? perm.principal_type}</td>
                  <td>{perm.principal}</td>
                  <td>{perm.permission === "write" ? "可管理" : "只读"}</td>
                  <td>
                    <button className="btn ghost tiny danger" onClick={() => removePermission(perm.id)}>移除</button>
                  </td>
                </tr>
              ))}
              {permissions.length === 0 && (
                <tr><td colSpan={4} className="empty-cell">暂无显式授权，当前仅创建人、归属部门与管理员可访问</td></tr>
              )}
            </tbody>
          </table>
        </Modal>
      )}
    </div>
  );
}
