import { FormEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ContextUsageIndicator } from "../components/ContextUsageIndicator";
import { TaskProgress } from "../components/TaskProgress";
import { ThinkingIndicator } from "../components/ThinkingIndicator";
import { useChatSSE } from "../hooks/useChatSSE";
import type { ContextUsage } from "../lib/contextUsage";
import { OnboardingForm } from "./OnboardingForm";

type Message = { role: "user" | "assistant"; content: string };

async function fetchSessionContext(sessionId: string): Promise<ContextUsage | null> {
  const r = await fetch(`/v1/sessions/${sessionId}/context`);
  if (!r.ok) return null;
  return r.json();
}

export function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(
    localStorage.getItem("session_id"),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [tasks, setTasks] = useState<{ id: string; title: string; status: string }[]>([]);
  const { sendMessage, loading } = useChatSSE();
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  const lastMessage = messages[messages.length - 1];
  const isThinking =
    loading &&
    (!lastMessage ||
      lastMessage.role === "user" ||
      (lastMessage.role === "assistant" && !lastMessage.content.trim()));

  useEffect(() => {
    if (!sessionId) return;
    void fetchSessionContext(sessionId).then((usage) => {
      if (usage) setContextUsage(usage);
    });
  }, [sessionId]);

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, loading, isThinking]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 96;
  }

  function applyContextUsage(usage: ContextUsage) {
    setContextUsage(usage);
    if (usage.recommend_new_session || usage.trimmed) {
      setNotice("对话较长，建议新开对话；档案与 HTML 仍保留。");
    }
  }

  async function refreshSession() {
    const r = await fetch("/v1/sessions/new", { method: "POST" });
    const data = await r.json();
    setSessionId(data.session_id);
    localStorage.setItem("session_id", data.session_id);
    setMessages([]);
    setTasks([]);
    setContextUsage(null);
    setNotice(null);
    stickToBottomRef.current = true;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userText = input.trim();
    setInput("");
    stickToBottomRef.current = true;
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    let assistant = "";

    await sendMessage(userText, sessionId, {
      onSession: (id) => {
        setSessionId(id);
        localStorage.setItem("session_id", id);
      },
      onToken: (delta) => {
        assistant += delta;
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            last.content = assistant;
            return [...next.slice(0, -1), last];
          }
          return [...next, { role: "assistant", content: assistant }];
        });
      },
      onHistoryNotice: applyContextUsage,
      onDone: async (payload) => {
        if (payload.context_usage) {
          applyContextUsage(payload.context_usage);
        }
        const taskRes = await fetch("/v1/tasks");
        if (taskRes.ok) {
          const data = await taskRes.json();
          setTasks(data.tasks || []);
        }
      },
      onError: async (message) => {
        if (message === "session_expired") await refreshSession();
      },
    });
  }

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col p-4">
      <header className="mb-4 shrink-0 flex items-center justify-between gap-3 overflow-visible">
        <h1 className="text-xl font-semibold">Career OS</h1>
        <div className="flex items-center gap-3 overflow-visible text-sm">
          <ContextUsageIndicator usage={contextUsage} />
          <button className="text-slate-400" onClick={() => setShowForm(true)}>
            建档
          </button>
          <button className="text-slate-400" onClick={refreshSession}>
            新会话
          </button>
          <Link className="text-emerald-400" to="/outputs">
            产物
          </Link>
        </div>
      </header>

      {notice && (
        <div className="mb-3 shrink-0 rounded border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
          {notice}
        </div>
      )}

      <div className="shrink-0">
        <TaskProgress tasks={tasks} />
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain py-4"
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`rounded-lg px-4 py-2 whitespace-pre-wrap break-words ${
              msg.role === "user" ? "ml-12 bg-emerald-900/40" : "mr-12 bg-slate-800"
            }`}
          >
            {msg.content}
            {loading && msg.role === "assistant" && idx === messages.length - 1 && msg.content ? (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-emerald-400/80 align-middle" />
            ) : null}
          </div>
        ))}
        {isThinking ? <ThinkingIndicator active={isThinking} /> : null}
      </div>

      <form onSubmit={onSubmit} className="flex shrink-0 gap-2 border-t border-slate-800 pt-4">
        <input
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入消息…（纯对话控制，无任务按钮/档位多选）"
          disabled={loading}
        />
        <button
          className="rounded-lg bg-emerald-600 px-4 py-2 disabled:opacity-50"
          disabled={loading}
          type="submit"
        >
          {loading ? "处理中…" : "发送"}
        </button>
      </form>

      {showForm && <OnboardingForm onClose={() => setShowForm(false)} />}
    </div>
  );
}
