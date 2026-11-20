import { useEffect, useMemo, useRef, useState } from "react";
import { api, streamChat, toMessage } from "../api";
import type { ChatMessage, Citation, Conversation, KB } from "../types";
import RichText from "../components/RichText";
import SourceDrawer from "../components/SourceDrawer";

const SUGGESTIONS = [
  "年假有几天，怎么在 OA 里申请？",
  "出差住宿费的报销标准是多少？",
  "OA 系统怎么提交报销单？",
  "合同付款账期和预付款比例有什么要求？",
];

export default function Chat() {
  const [kbs, setKbs] = useState<KB[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drawer, setDrawer] = useState<Citation | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadConversations = () =>
    api.get<Conversation[]>("/api/conversations").then(setConversations).catch(() => undefined);

  useEffect(() => {
    api.get<KB[]>("/api/kbs").then((list) => {
      setKbs(list);
      setSelected(list.map((kb) => kb.id));
    });
    loadConversations();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const openConversation = async (id: number) => {
    setError("");
    try {
      const data = await api.get<{ messages: Record<string, unknown>[] }>(`/api/conversations/${id}`);
      setActiveId(id);
      setMessages(data.messages.map(toMessage));
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载会话失败");
    }
  };

  const newConversation = () => {
    setActiveId(null);
    setMessages([]);
    setError("");
  };

  const removeConversation = async (id: number, event: React.MouseEvent) => {
    event.stopPropagation();
    if (!window.confirm("删除该会话记录？")) return;
    await api.del(`/api/conversations/${id}`);
    if (activeId === id) newConversation();
    loadConversations();
  };

  const send = async (text?: string) => {
    const content = (text ?? question).trim();
    if (!content || busy) return;
    if (selected.length === 0) {
      setError("请至少选择一个知识库");
      return;
    }
    setError("");
    setQuestion("");
    setBusy(true);
    const userMessage: ChatMessage = { role: "user", content, citations: [] };
    const assistantMessage: ChatMessage = { role: "assistant", content: "", citations: [] };
    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    try {
      await streamChat(
        { question: content, conversation_id: activeId, kb_ids: selected },
        {
          onMeta: (meta) => setActiveId(meta.conversation_id),
          onCitations: (citations) =>
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], citations };
              return next;
            }),
          onToken: (token) =>
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + token };
              return next;
            }),
          onDone: (info) =>
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = {
                ...next[next.length - 1],
                provider: info.provider,
                latency_ms: info.latency_ms,
              };
              return next;
            }),
        },
      );
      loadConversations();
    } catch (err) {
      setMessages((prev) => prev.slice(0, -1));
      setError(err instanceof Error ? err.message : "问答失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  };

  const toggleKb = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const allSelected = kbs.length > 0 && selected.length === kbs.length;
  const scopeLabel = useMemo(() => {
    if (!kbs.length) return "加载中…";
    if (allSelected) return `全部可访问知识库（${kbs.length}）`;
    return `已选择 ${selected.length} / ${kbs.length} 个知识库`;
  }, [kbs.length, selected.length, allSelected]);

  return (
    <div className="chat-layout">
      <aside className="chat-rail">
        <button className="btn primary block" onClick={newConversation}>
          + 新会话
        </button>
        <div className="rail-title">会话记录</div>
        <div className="rail-list">
          {conversations.length === 0 && <div className="muted small">暂无历史会话</div>}
          {conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`rail-item ${activeId === conversation.id ? "active" : ""}`}
              onClick={() => openConversation(conversation.id)}
            >
              <div className="rail-item-main">
                <span>{conversation.title}</span>
                <em>{conversation.message_count} 条</em>
              </div>
              <button className="mini-btn" onClick={(event) => removeConversation(conversation.id, event)}>
                删除
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        <div className="scope-bar">
          <div className="scope-label">
            <span className="scope-icon">⌘</span>
            <div>
              <strong>检索范围</strong>
              <em>{scopeLabel}</em>
            </div>
          </div>
          <div className="scope-chips">
            <button
              className={`chip-btn ${allSelected ? "on" : ""}`}
              onClick={() => setSelected(allSelected ? [] : kbs.map((kb) => kb.id))}
            >
              全部
            </button>
            {kbs.map((kb) => (
              <button
                key={kb.id}
                className={`chip-btn ${selected.includes(kb.id) ? "on" : ""}`}
                onClick={() => toggleKb(kb.id)}
                title={kb.description}
              >
                {kb.name}
                {kb.visibility === "restricted" && <span className="lock">受限</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-badge">AI 知识库助手</div>
              <h2>今天想了解哪项制度或操作？</h2>
              <p>
                回答仅基于你有权限访问的企业资料，并标注原文出处。涉及合同与资金事项时，
                系统会提示人工审核。
              </p>
              <div className="suggestion-grid">
                {SUGGESTIONS.map((item) => (
                  <button key={item} className="suggestion" onClick={() => send(item)}>
                    <span>{item}</span>
                    <em>→</em>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) =>
            message.role === "user" ? (
              <div key={index} className="msg user">
                <div className="bubble">{message.content}</div>
              </div>
            ) : (
              <div key={index} className="msg assistant">
                <div className="assistant-avatar">AI</div>
                <div className="assistant-body">
                  {message.content ? (
                    <RichText
                      text={message.content}
                      onCite={(number) => {
                        const citation = message.citations.find((item) => item.index === number);
                        if (citation) setDrawer(citation);
                      }}
                    />
                  ) : (
                    <div className="typing">
                      <span />
                      <span />
                      <span />
                    </div>
                  )}
                  {message.citations.length > 0 && (
                    <div className="citations">
                      <div className="citations-title">资料来源</div>
                      <div className="citation-grid">
                        {message.citations.map((citation) => (
                          <button
                            key={citation.chunk_id}
                            className="citation-card"
                            onClick={() => setDrawer(citation)}
                          >
                            <span className="citation-index">{citation.index}</span>
                            <div>
                              <strong>{citation.doc_title}</strong>
                              <em>
                                {citation.section || "正文"} · 第 {citation.page} 页
                              </em>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {message.content && (
                    <div className="answer-meta">
                      {message.provider?.startsWith("openai") ? "大模型生成" : "本地检索整理"}
                      {message.latency_ms ? ` · ${message.latency_ms} ms` : ""}
                      {message.citations.length ? ` · ${message.citations.length} 条来源` : ""}
                    </div>
                  )}
                </div>
              </div>
            ),
          )}
        </div>

        {error && <div className="alert error compact">{error}</div>}

        <div className="composer">
          <textarea
            value={question}
            placeholder="输入问题，例如：合同付款账期有什么要求？"
            rows={2}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <button className="btn primary send" onClick={() => send()} disabled={busy || !question.trim()}>
            {busy ? "生成中…" : "发送"}
          </button>
        </div>
        <div className="composer-tip">
          Enter 发送 · Shift + Enter 换行 · 答案由企业资料检索生成，请以正式文件为准
        </div>
      </section>

      {drawer && <SourceDrawer citation={drawer} onClose={() => setDrawer(null)} />}
    </div>
  );
}
