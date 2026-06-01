import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSession,
  deleteSession,
  listSessions,
  patchSession,
  SessionApiError,
  type SessionRow,
} from "../lib/sessionsApi";

type Props = {
  currentSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: (sessionId: string) => void;
  onSessionCleared?: () => void;
  refreshTrigger?: number;
};

export function SessionSwitcher({
  currentSessionId,
  onSelectSession,
  onNewSession,
  onSessionCleared,
  refreshTrigger = 0,
}: Props) {
  const [search, setSearch] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSessions({
        archived: "all",
        q: debouncedQ || undefined,
      });
      setSessions(data.sessions);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [debouncedQ]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    void loadList();
  }, [refreshTrigger, loadList]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQ(search.trim()), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search]);

  async function handleNew() {
    try {
      const { session_id } = await createSession();
      onNewSession(session_id);
      void loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "新建失败");
    }
  }

  async function handleRename(row: SessionRow) {
    const next = window.prompt("重命名会话", row.title);
    if (next === null) return;
    const title = next.trim();
    if (!title || title.length > 32) {
      window.alert("标题须为 1–32 个字符");
      return;
    }
    try {
      await patchSession(row.session_id, { title });
      void loadList();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "重命名失败");
    }
  }

  async function handleArchiveToggle(row: SessionRow) {
    try {
      await patchSession(row.session_id, { archived: !row.archived });
      void loadList();
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "操作失败");
    }
  }

  async function handleDelete(row: SessionRow) {
    const ok = window.confirm(
      `确定删除「${row.title}」？对话记录与关联任务进度将永久删除，档案与 HTML 产物保留。`,
    );
    if (!ok) return;
    try {
      await deleteSession(row.session_id);
      void loadList();
      if (row.session_id === currentSessionId) {
        const remaining = sessions.filter((s) => s.session_id !== row.session_id);
        if (remaining.length > 0) {
          onSelectSession(remaining[0].session_id);
          return;
        }
        const fresh = await listSessions({ archived: "all" });
        const next = fresh.sessions.find((s) => s.session_id !== row.session_id);
        if (next) {
          onSelectSession(next.session_id);
        } else {
          onSessionCleared?.();
        }
      }
    } catch (e) {
      if (e instanceof SessionApiError && e.status === 409 && e.message === "chat_in_progress") {
        window.alert("会话仍在处理中，暂时无法删除。");
        return;
      }
      window.alert(e instanceof Error ? e.message : "删除失败");
    }
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950">
      <div className="border-b border-slate-800 px-3 py-3">
        <h2 className="mb-3 font-medium text-slate-100">会话</h2>
        <input
          type="search"
          placeholder="搜索标题或预览…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-2 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
        />
        <button
          type="button"
          className="w-full rounded bg-emerald-700 py-2 text-sm text-white hover:bg-emerald-600"
          onClick={() => void handleNew()}
        >
          新建会话
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {error ? (
          <p className="px-2 py-4 text-sm text-rose-300">{error}</p>
        ) : loading ? (
          <p className="px-2 py-4 text-sm text-slate-500">加载中…</p>
        ) : sessions.length === 0 ? (
          <p className="px-2 py-4 text-sm text-slate-500">暂无会话</p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((row) => (
              <li key={row.session_id}>
                <div
                  className={`rounded-lg border px-3 py-2 ${
                    row.session_id === currentSessionId
                      ? "border-emerald-700/60 bg-emerald-950/30"
                      : "border-transparent hover:border-slate-700 hover:bg-slate-900/80"
                  }`}
                >
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => onSelectSession(row.session_id)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="truncate font-medium text-slate-100">
                        {row.title || "未命名会话"}
                      </span>
                      <span className="flex shrink-0 gap-1">
                        {row.expired ? (
                          <span className="rounded bg-rose-900/60 px-1 text-[10px] text-rose-200">
                            过期
                          </span>
                        ) : null}
                        {row.archived ? (
                          <span className="rounded bg-slate-700 px-1 text-[10px] text-slate-300">
                            归档
                          </span>
                        ) : null}
                      </span>
                    </div>
                    {row.preview ? (
                      <p className="mt-0.5 truncate text-xs text-slate-500">{row.preview}</p>
                    ) : null}
                    {row.message_count != null ? (
                      <p className="mt-0.5 text-[10px] text-slate-600">
                        {row.message_count} 条消息
                      </p>
                    ) : null}
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    <button
                      type="button"
                      className="text-slate-400 hover:text-emerald-400"
                      onClick={() => void handleRename(row)}
                    >
                      重命名
                    </button>
                    <button
                      type="button"
                      className="text-slate-400 hover:text-emerald-400"
                      onClick={() => void handleArchiveToggle(row)}
                    >
                      {row.archived ? "取消归档" : "归档"}
                    </button>
                    <button
                      type="button"
                      className="text-rose-400/80 hover:text-rose-300"
                      onClick={() => void handleDelete(row)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
