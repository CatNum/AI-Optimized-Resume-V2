import { useEffect, useMemo, useState } from "react";
import {
  activityStatusLabel,
  type SessionActivity,
  type SessionActivityItem,
} from "../lib/sessionActivity";
import { getTasks, type TaskListRow, type TaskRow } from "../lib/sessionsApi";

const LIST_TYPE_HEADLINES: Record<string, string> = {
  explore: "职业初探",
  jd: "JD 评估",
  plan: "职业规划",
};

function mapTaskStatus(status: string): SessionActivityItem["status"] {
  if (status === "active") return "in_progress";
  if (status === "completed") return "completed";
  return "pending";
}

/** D3: active list with tasks → latest ready with tasks → null */
export function pickTaskListForDisplay(lists: TaskListRow[]): TaskListRow | null {
  const active = lists.find((l) => l.status === "active");
  if (active?.tasks?.length) return active;

  const ready = lists.filter((l) => l.status === "ready");
  if (ready[0]?.tasks?.length) return ready[0];

  return null;
}

function tasksToActivity(list: TaskListRow): SessionActivity {
  const headline =
    (list.list_type && LIST_TYPE_HEADLINES[list.list_type]) || null;
  return {
    list_type: list.list_type,
    headline,
    items: list.tasks.map((t: TaskRow) => ({
      id: t.id,
      title: t.title,
      status: mapTaskStatus(t.status),
    })),
  };
}

export function TaskProgress({
  sessionId,
  activity,
}: {
  sessionId: string | null;
  activity: SessionActivity | null;
}) {
  const [fetchedActivity, setFetchedActivity] = useState<SessionActivity | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setFetchedActivity(null);
      return;
    }
    let cancelled = false;
    void getTasks(sessionId)
      .then((body) => {
        if (cancelled) return;
        const list = pickTaskListForDisplay(body.lists);
        setFetchedActivity(list ? tasksToActivity(list) : null);
      })
      .catch(() => {
        if (!cancelled) setFetchedActivity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const display = useMemo(() => {
    if (fetchedActivity?.items?.length) {
      return {
        ...fetchedActivity,
        headline: fetchedActivity.headline ?? activity?.headline ?? null,
      };
    }
    if (activity?.items?.length) return activity;
    return null;
  }, [fetchedActivity, activity]);

  if (!display?.items?.length) return null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm">
      {display.headline ? (
        <div className="mb-2 text-emerald-300/90">{display.headline}</div>
      ) : (
        <div className="mb-2 font-medium text-slate-300">任务进度</div>
      )}
      <ul className="space-y-1">
        {display.items.map((item) => (
          <li key={item.id} className="flex justify-between gap-3 text-slate-400">
            <span>{item.title || item.id}</span>
            <span
              className={
                item.status === "in_progress"
                  ? "text-emerald-400"
                  : item.status === "completed"
                    ? "text-slate-500"
                    : ""
              }
            >
              {activityStatusLabel(item.status)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
