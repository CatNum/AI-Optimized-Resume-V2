import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ContextUsageIndicator } from "../components/ContextUsageIndicator";
import { TaskProgress } from "../components/TaskProgress";
import { ThinkingIndicator } from "../components/ThinkingIndicator";
import { useChatSSE } from "../hooks/useChatSSE";
import type { ContextUsage } from "../lib/contextUsage";
import type { SessionActivity } from "../lib/sessionActivity";
import { ExploreIntakeForm } from "./ExploreIntakeForm";
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
  const [showExploreIntake, setShowExploreIntake] = useState(false);
  const [sessionActivity, setSessionActivity] = useState<SessionActivity | null>(null);
  const { sendMessage, loading } = useChatSSE();
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const pendingExploreMessageRef = useRef<string | null>(null);

  const lastMessage = messages[messages.length - 1];
  const isThinking =
    loading &&
    (!lastMessage ||
      lastMessage.role === "user" ||
      (lastMessage.role === "assistant" && !lastMessage.content.trim()));

  useEffect(() => {
    if (!sessionId) return;
    void fetchSessionContext(sessionId).then((usage) => {
      if (!usage) return;
      applyContextUsage(usage);
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
    if (usage.session_activity?.items?.length) {
      setSessionActivity(usage.session_activity);
    }
    if (usage.recommend_new_session) {
      setNotice("对话较长，建议新开对话；档案与 HTML 仍保留。");
    } else if (usage.trimmed) {
      setNotice("较早的对话未纳入当前上下文；如有遗漏可简要复述。");
    }
  }

  async function refreshSession() {
    const r = await fetch("/v1/sessions/new", { method: "POST" });
    const data = await r.json();
    setSessionId(data.session_id);
    localStorage.setItem("session_id", data.session_id);
    setMessages([]);
    setSessionActivity(null);
    setContextUsage(null);
    setNotice(null);
    stickToBottomRef.current = true;
  }

  async function dispatchChat(userText: string, appendUserMessage: boolean) {
    if (!userText.trim() || loading) return;
    stickToBottomRef.current = true;
    if (appendUserMessage) {
      setMessages((prev) => [...prev, { role: "user", content: userText.trim() }]);
    }
    let assistant = "";

    await sendMessage(userText.trim(), sessionId, {
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
      onExploreIntake: () => {
        pendingExploreMessageRef.current = userText.trim();
        setShowExploreIntake(true);
      },
      onDone: async (payload) => {
        if (payload.context_usage) {
          applyContextUsage(payload.context_usage);
        }
      },
      onError: async (message) => {
        if (message === "session_expired") await refreshSession();
      },
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userText = input.trim();
    setInput("");
    await dispatchChat(userText, true);
  }

  async function handleExploreIntakeSubmitted() {
    const pending = pendingExploreMessageRef.current;
    pendingExploreMessageRef.current = null;
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: "【已提交初探信息表】简历与补充信息已填写，请继续职业初探。",
      },
    ]);
    if (!pending) return;
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    await dispatchChat(pending, false);
  }

  function handleInputKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    e.preventDefault();
    if (!input.trim() || loading) return;
    void onSubmit(e as unknown as FormEvent);
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
        <TaskProgress activity={sessionActivity} />
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
        <textarea
          className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 leading-relaxed"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder="输入消息… Enter 发送，Shift+Enter 换行"
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
      {showExploreIntake && (
        <ExploreIntakeForm
          onClose={() => setShowExploreIntake(false)}
          onSubmitted={() => void handleExploreIntakeSubmitted()}
        />
      )}
    </div>
  );
}
