import {
  DragEvent,
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  FILE_REF_MIME,
  type FileRefAttachment,
  formatAttachmentsForMessage,
  parseFileRefFromDataTransfer,
} from "../lib/chatAttachments";
import { ContextUsageIndicator } from "../components/ContextUsageIndicator";
import { OutputsPanel } from "../components/OutputsPanel";
import { SessionSwitcher } from "../components/SessionSwitcher";
import { TaskProgress } from "../components/TaskProgress";
import { ThinkingIndicator } from "../components/ThinkingIndicator";
import { useChatSSE } from "../hooks/useChatSSE";
import type { ContextUsage } from "../lib/contextUsage";
import {
  getMessages,
  listSessions,
  SessionApiError,
  type SessionRow,
} from "../lib/sessionsApi";
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
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<FileRefAttachment[]>([]);
  const [dropActive, setDropActive] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [showExploreIntake, setShowExploreIntake] = useState(false);
  const [initDone, setInitDone] = useState(false);
  const [sessionRefreshTrigger, setSessionRefreshTrigger] = useState(0);
  const [taskRefreshTrigger, setTaskRefreshTrigger] = useState(0);
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
    if (usage.recommend_new_session || usage.over_limit) {
      setNotice("对话较长，建议新开对话；档案与 HTML 仍保留。");
    }
  }, []);

  const loadSessionView = useCallback(
    async (id: string) => {
      const msgRes = await getMessages(id);
      setMessages(msgRes.messages);
      const usage = await fetchSessionContext(id);
      if (usage) applyContextUsage(usage);
      else setContextUsage(null);
    },
    [applyContextUsage],
  );

  const resolveInitialSession = useCallback(async () => {
    const { sessions } = await listSessions({ archived: "all" });
    const stored = localStorage.getItem("session_id");
    const selected = pickInitialSessionId(stored, sessions);
    setSessionId(selected);
    if (!selected) {
      setMessages([]);
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

  function addAttachment(ref: FileRefAttachment) {
    setAttachments((prev) =>
      prev.some((a) => a.path === ref.path) ? prev : [...prev, ref],
    );
  }

  function removeAttachment(path: string) {
    setAttachments((prev) => prev.filter((a) => a.path !== path));
  }

  function clearSessionWorkspace() {
    setMessages([]);
    setInput("");
    setAttachments([]);
    setContextUsage(null);
    setNotice(null);
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
  }

  function handleSessionCleared() {
    localStorage.removeItem("session_id");
    setSessionId(null);
    clearSessionWorkspace();
  }

  function shouldApplyStreamUpdate(streamSessionId: string | null): boolean {
    return streamSessionId === displayedSessionIdRef.current;
  }

  async function dispatchChat(
    userText: string,
    appendUserMessage: boolean,
    refs: FileRefAttachment[] = [],
  ) {
    const trimmed = userText.trim();
    if ((!trimmed && refs.length === 0) || chatBusyOnDisplayed) return;
    const apiMessage = trimmed || "请基于引用的简历继续处理。";
    const bubbleText = trimmed + formatAttachmentsForMessage(refs);
    stickToBottomRef.current = true;
    const streamAtStart = sessionId;
    inFlightSessionIdRef.current = streamAtStart;
    let streamSessionId: string | null = streamAtStart;

    if (appendUserMessage && shouldApplyStreamUpdate(streamSessionId)) {
      setMessages((prev) => [...prev, { role: "user", content: bubbleText }]);
    }
    let assistant = "";

    await sendMessage(apiMessage, sessionId, {
      onSession: (id) => {
        streamSessionId = id;
        inFlightSessionIdRef.current = id;
        const displayed = displayedSessionIdRef.current;
        if (displayed === streamAtStart || (streamAtStart === null && displayed === null)) {
          setSessionId(id);
          localStorage.setItem("session_id", id);
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
        if (streamSessionId && shouldApplyStreamUpdate(streamSessionId)) {
          setSessionRefreshTrigger((n) => n + 1);
          setTaskRefreshTrigger((n) => n + 1);
        }
      },
      onError: (message) => {
        if (message === "chat_in_progress") {
          setNotice("上一条仍在处理中，请稍候。");
        }
      },
    }, refs);
    inFlightSessionIdRef.current = null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if ((!input.trim() && attachments.length === 0) || chatBusyOnDisplayed) return;
    const userText = input.trim();
    const refs = attachments;
    setInput("");
    setAttachments([]);
    await dispatchChat(userText, true, refs);
  }

  async function handleExploreIntakeSubmitted() {
    setTaskRefreshTrigger((n) => n + 1);
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
    if ((!input.trim() && attachments.length === 0) || chatBusyOnDisplayed) return;
    void onSubmit(e as unknown as FormEvent);
  }

  function handleDragOver(e: DragEvent) {
    if (!e.dataTransfer.types.includes(FILE_REF_MIME)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDropActive(true);
  }

  function handleDragLeave(e: DragEvent) {
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDropActive(false);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDropActive(false);
    const ref = parseFileRefFromDataTransfer(e.dataTransfer);
    if (ref) addAttachment(ref);
  }

  const canSend = (input.trim().length > 0 || attachments.length > 0) && !chatBusyOnDisplayed;
  const inputDisabled = chatBusyOnDisplayed || !initDone;

  return (
    <div className="flex h-screen bg-slate-950">
      <SessionSwitcher
        currentSessionId={sessionId}
        refreshTrigger={sessionRefreshTrigger}
        onSelectSession={(id) => void activateSession(id)}
        onNewSession={(id) => void handleNewSession(id)}
        onSessionCleared={handleSessionCleared}
      />

      <div className="flex min-w-0 flex-1 flex-col p-4">
        <header className="mb-4 flex shrink-0 items-center justify-between gap-3">
          <h1 className="shrink-0 text-xl font-semibold">Career OS</h1>
          <div className="flex items-center gap-3 text-sm">
            <ContextUsageIndicator usage={contextUsage} />
            <button className="text-slate-400 hover:text-slate-200" onClick={() => setShowForm(true)}>
              建档
            </button>
          </div>
        </header>

      {notice ? (
        <div className="mb-3 shrink-0 rounded border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
          {notice}
        </div>
      ) : null}

      <div className="shrink-0">
        <TaskProgress sessionId={sessionId} refreshTrigger={taskRefreshTrigger} />
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

      <form
        onSubmit={onSubmit}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex shrink-0 flex-col gap-2 border-t border-slate-800 pt-4 ${
          dropActive ? "rounded-lg ring-1 ring-emerald-600/60" : ""
        }`}
      >
        {attachments.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {attachments.map((att) => (
              <span
                key={att.path}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-emerald-800/60 bg-emerald-950/50 px-2 py-1 text-xs text-emerald-100"
                title={att.path}
              >
                <span className="truncate">
                  {att.label || att.path.split("/").pop()}
                </span>
                <button
                  type="button"
                  className="shrink-0 text-emerald-300/80 hover:text-emerald-100"
                  aria-label="移除引用"
                  onClick={() => removeAttachment(att.path)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <div className="flex gap-2">
          <textarea
            className="flex-1 resize-none rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 leading-relaxed disabled:opacity-50"
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="输入消息… 可从右侧拖入简历引用；Enter 发送"
            disabled={inputDisabled}
          />
          <button
            className="rounded-lg bg-emerald-600 px-4 py-2 disabled:opacity-50"
            disabled={inputDisabled || !canSend}
            type="submit"
          >
            {chatBusyOnDisplayed ? "处理中…" : "发送"}
          </button>
        </div>
      </form>

      {showForm && <OnboardingForm onClose={() => setShowForm(false)} />}
      {showExploreIntake && sessionId ? (
        <ExploreIntakeForm
          sessionId={sessionId}
          onClose={() => setShowExploreIntake(false)}
          onSubmitted={() => void handleExploreIntakeSubmitted()}
        />
      ) : null}
      </div>

      <OutputsPanel refreshTrigger={taskRefreshTrigger} />
    </div>
  );
}
