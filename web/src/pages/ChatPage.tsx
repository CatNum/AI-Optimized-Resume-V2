import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ContextUsageIndicator } from "../components/ContextUsageIndicator";
import { ExpiredSessionBanner } from "../components/ExpiredSessionBanner";
import { SessionSwitcher } from "../components/SessionSwitcher";
import { TaskProgress } from "../components/TaskProgress";
import { ThinkingIndicator } from "../components/ThinkingIndicator";
import { useChatSSE } from "../hooks/useChatSSE";
import type { ContextUsage } from "../lib/contextUsage";
import {
  createSession,
  getMessages,
  getSession,
  listSessions,
  SessionApiError,
  type SessionRow,
} from "../lib/sessionsApi";
import type { SessionActivity } from "../lib/sessionActivity";
import { ExploreIntakeForm } from "./ExploreIntakeForm";
import { OnboardingForm } from "./OnboardingForm";

type Message = { role: "user" | "assistant"; content: string };

async function fetchSessionContext(sessionId: string): Promise<ContextUsage | null> {
  const r = await fetch(`/v1/sessions/${sessionId}/context`);
  if (!r.ok) return null;
  return r.json();
}

function pickInitialSessionId(
  stored: string | null,
  sessions: SessionRow[],
): string | null {
  if (stored && sessions.some((s) => s.session_id === stored)) {
    return stored;
  }
  if (stored) localStorage.removeItem("session_id");
  if (sessions.length > 0) return sessions[0].session_id;
  return null;
}

export function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string | undefined>();
  const [sessionExpired, setSessionExpired] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showExploreIntake, setShowExploreIntake] = useState(false);
  const [sessionActivity, setSessionActivity] = useState<SessionActivity | null>(null);
  const [initDone, setInitDone] = useState(false);
  const [drawerOpenTrigger, setDrawerOpenTrigger] = useState(0);
  const { sendMessage, loading } = useChatSSE();
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const pendingExploreMessageRef = useRef<string | null>(null);
  const displayedSessionIdRef = useRef<string | null>(null);
  const inFlightSessionIdRef = useRef<string | null>(null);

  displayedSessionIdRef.current = sessionId;

  const lastMessage = messages[messages.length - 1];
  const chatBusyOnDisplayed =
    loading &&
    (inFlightSessionIdRef.current === null
      ? sessionId === null
      : inFlightSessionIdRef.current === sessionId);
  const isThinking =
    chatBusyOnDisplayed &&
    (!lastMessage ||
      lastMessage.role === "user" ||
      (lastMessage.role === "assistant" && !lastMessage.content.trim()));

  const applyContextUsage = useCallback((usage: ContextUsage) => {
    setContextUsage(usage);
    if (usage.session_activity?.items?.length) {
      setSessionActivity(usage.session_activity);
    }
    if (usage.recommend_new_session) {
      setNotice("对话较长，建议新开对话；档案与 HTML 仍保留。");
    } else if (usage.trimmed) {
      setNotice("较早的对话未纳入当前上下文；如有遗漏可简要复述。");
    }
  }, []);

  const loadSessionView = useCallback(
    async (id: string) => {
      const [msgRes, sessionRow] = await Promise.all([getMessages(id), getSession(id)]);
      setMessages(msgRes.messages);
      setSessionTitle(sessionRow.title);
      setSessionExpired(Boolean(sessionRow.expired ?? msgRes.expired));
      const usage = await fetchSessionContext(id);
      if (usage) applyContextUsage(usage);
      else {
        setContextUsage(null);
        setSessionActivity(null);
      }
    },
    [applyContextUsage],
  );

  const resolveInitialSession = useCallback(async () => {
    const { sessions } = await listSessions();
    const stored = localStorage.getItem("session_id");
    const selected = pickInitialSessionId(stored, sessions);
    setSessionId(selected);
    if (!selected) {
      setSessionExpired(false);
      setMessages([]);
      setSessionTitle(undefined);
      setInitDone(true);
      return;
    }
    localStorage.setItem("session_id", selected);
    try {
      await loadSessionView(selected);
    } catch (e) {
      if (e instanceof SessionApiError && e.status === 404) {
        localStorage.removeItem("session_id");
        const fallback = pickInitialSessionId(null, sessions.filter((s) => s.session_id !== selected));
        setSessionId(fallback);
        if (fallback) {
          localStorage.setItem("session_id", fallback);
          await loadSessionView(fallback);
        } else {
          setMessages([]);
          setSessionExpired(false);
        }
      }
    } finally {
      setInitDone(true);
    }
  }, [loadSessionView]);

  useEffect(() => {
    void resolveInitialSession();
  }, [resolveInitialSession]);

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

  function clearSessionWorkspace() {
    setMessages([]);
    setSessionActivity(null);
    setContextUsage(null);
    setNotice(null);
    setSessionExpired(false);
    stickToBottomRef.current = true;
  }

  async function activateSession(id: string) {
    setSessionId(id);
    localStorage.setItem("session_id", id);
    clearSessionWorkspace();
    await loadSessionView(id);
  }

  async function handleNewSession(id: string) {
    setSessionId(id);
    localStorage.setItem("session_id", id);
    clearSessionWorkspace();
    setSessionTitle("未命名会话");
    try {
      const row = await getSession(id);
      setSessionTitle(row.title);
      setSessionExpired(Boolean(row.expired));
    } catch {
      /* ignore */
    }
  }

  function handleSessionCleared() {
    localStorage.removeItem("session_id");
    setSessionId(null);
    clearSessionWorkspace();
    setSessionTitle(undefined);
  }

  function shouldApplyStreamUpdate(streamSessionId: string | null): boolean {
    return streamSessionId === displayedSessionIdRef.current;
  }

  async function dispatchChat(userText: string, appendUserMessage: boolean) {
    if (!userText.trim() || chatBusyOnDisplayed || sessionExpired) return;
    stickToBottomRef.current = true;
    const streamAtStart = sessionId;
    inFlightSessionIdRef.current = streamAtStart;
    let streamSessionId: string | null = streamAtStart;

    if (appendUserMessage && shouldApplyStreamUpdate(streamSessionId)) {
      setMessages((prev) => [...prev, { role: "user", content: userText.trim() }]);
    }
    let assistant = "";

    await sendMessage(userText.trim(), sessionId, {
      onSession: (id) => {
        streamSessionId = id;
        inFlightSessionIdRef.current = id;
        const displayed = displayedSessionIdRef.current;
        if (displayed === streamAtStart || (streamAtStart === null && displayed === null)) {
          setSessionId(id);
          localStorage.setItem("session_id", id);
          setSessionExpired(false);
        }
      },
      onToken: (delta) => {
        if (!shouldApplyStreamUpdate(streamSessionId)) return;
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
      onHistoryNotice: (payload) => {
        if (shouldApplyStreamUpdate(streamSessionId)) applyContextUsage(payload);
      },
      onExploreIntake: () => {
        if (!shouldApplyStreamUpdate(streamSessionId)) return;
        pendingExploreMessageRef.current = userText.trim();
        setShowExploreIntake(true);
      },
      onDone: async (payload) => {
        if (shouldApplyStreamUpdate(streamSessionId) && payload.context_usage) {
          applyContextUsage(payload.context_usage);
        }
      },
      onError: (message) => {
        if (message === "session_expired") {
          if (shouldApplyStreamUpdate(streamSessionId)) {
            setSessionExpired(true);
          }
          return;
        }
        if (message === "chat_in_progress") {
          setNotice("上一条仍在处理中，请稍候。");
        }
      },
    });
    inFlightSessionIdRef.current = null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || chatBusyOnDisplayed || sessionExpired) return;
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
    if (!input.trim() || chatBusyOnDisplayed || sessionExpired) return;
    void onSubmit(e as unknown as FormEvent);
  }

  const inputDisabled = chatBusyOnDisplayed || sessionExpired || !initDone;

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col p-4">
      <header className="mb-4 shrink-0 flex items-center justify-between gap-3 overflow-visible">
        <h1 className="text-xl font-semibold shrink-0">Career OS</h1>
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2 overflow-visible text-sm">
          <SessionSwitcher
            currentSessionId={sessionId}
            currentTitle={sessionTitle}
            openTrigger={drawerOpenTrigger}
            onSelectSession={(id) => void activateSession(id)}
            onNewSession={(id) => void handleNewSession(id)}
            onSessionCleared={handleSessionCleared}
          />
          <ContextUsageIndicator usage={contextUsage} />
          <button className="shrink-0 text-slate-400" onClick={() => setShowForm(true)}>
            建档
          </button>
          <button
            className="shrink-0 text-slate-400"
            onClick={() =>
              void createSession().then(({ session_id }) => handleNewSession(session_id))
            }
          >
            新会话
          </button>
          <Link className="shrink-0 text-emerald-400" to="/outputs">
            产物
          </Link>
        </div>
      </header>

      {sessionExpired ? (
        <ExpiredSessionBanner
          onSwitchSession={() => setDrawerOpenTrigger((n) => n + 1)}
          onNewSession={async () => {
            const { session_id } = await createSession();
            await handleNewSession(session_id);
          }}
        />
      ) : null}

      {notice && !sessionExpired ? (
        <div className="mb-3 shrink-0 rounded border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
          {notice}
        </div>
      ) : null}

      <div className="shrink-0">
        <TaskProgress activity={sessionActivity} />
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain py-4"
      >
        {initDone && messages.length === 0 && !chatBusyOnDisplayed ? (
          <p className="text-center text-sm text-slate-500">
            {sessionId ? "暂无消息，开始对话吧。" : "发送首条消息将自动创建会话。"}
          </p>
        ) : null}
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`rounded-lg px-4 py-2 whitespace-pre-wrap break-words ${
              msg.role === "user" ? "ml-12 bg-emerald-900/40" : "mr-12 bg-slate-800"
            }`}
          >
            {msg.content}
            {chatBusyOnDisplayed &&
            msg.role === "assistant" &&
            idx === messages.length - 1 &&
            msg.content ? (
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-emerald-400/80 align-middle" />
            ) : null}
          </div>
        ))}
        {isThinking ? <ThinkingIndicator active={isThinking} /> : null}
      </div>

      <form onSubmit={onSubmit} className="flex shrink-0 gap-2 border-t border-slate-800 pt-4">
        <textarea
          className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 leading-relaxed disabled:opacity-50"
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleInputKeyDown}
          placeholder={
            sessionExpired
              ? "会话已过期，请切换或新建会话"
              : "输入消息… Enter 发送，Shift+Enter 换行"
          }
          disabled={inputDisabled}
        />
        <button
          className="rounded-lg bg-emerald-600 px-4 py-2 disabled:opacity-50"
          disabled={inputDisabled}
          type="submit"
        >
          {chatBusyOnDisplayed ? "处理中…" : "发送"}
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
