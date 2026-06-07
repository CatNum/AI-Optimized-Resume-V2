import { useEffect, useState } from "react";
import {
  getTasks,
  type MilestoneRow,
  type SessionTasksResponse,
  type TaskListRow,
} from "../lib/sessionsApi";

const PHASE_LABELS: Record<string, string> = {
  explore: "职业初探",
  market: "市场分析",
  jd_analysis: "JD 分析",
  resume_strategy: "简历优化策略",
  resume_optimize: "简历优化",
};

const PHASE_ORDER = [
  "explore",
  "market",
  "jd_analysis",
  "resume_strategy",
  "resume_optimize",
];

function pickPipelineList(body: SessionTasksResponse): TaskListRow | null {
  const active = body.lists.find(
    (l) => l.status === "active" && l.list_type === "pipeline",
  );
  if (active) return active;
  return body.lists.find((l) => l.list_type === "pipeline") ?? null;
}

function phaseIndex(phase: string): number {
  return PHASE_ORDER.indexOf(phase);
}

function milestoneState(
  ms: MilestoneRow,
  list: TaskListRow,
): "other" | "current" | "disabled" {
  const currentIndex = phaseIndex(list.current_phase ?? "explore");
  const index = phaseIndex(ms.pipeline_phase);
  if (index === currentIndex) return "current";
  if (index >= 0 && currentIndex >= 0 && index < currentIndex) return "other";
  return "disabled";
}

export function TaskProgress({
  sessionId,
  refreshTrigger = 0,
}: {
  sessionId: string | null;
  refreshTrigger?: number;
}) {
  const [payload, setPayload] = useState<SessionTasksResponse | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setPayload(null);
      return;
    }
    let cancelled = false;
    void getTasks(sessionId)
      .then((body) => {
        if (!cancelled) setPayload(body);
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, refreshTrigger]);

  if (!payload) return null;

  const list = pickPipelineList(payload);
  if (!list?.milestones?.length) return null;

  const weak = payload.ui_mode === "weak";

  return (
    <section
      className={`task-progress ${weak ? "task-progress--weak" : ""}`}
      aria-label="任务进度"
    >
      {weak ? (
        <p className="task-progress__hint">请先完成建档 / 初探表单后再推进后续步骤</p>
      ) : null}
      <ol className="task-progress__milestones">
        {list.milestones.map((ms) => {
          const state = milestoneState(ms, list);
          const isCurrent = state === "current";
          const hasWorks = isCurrent && ms.works.length > 0;
          return (
            <li
              key={ms.task_id}
              className={[
                "task-progress__milestone",
                `task-progress__milestone--${state}`,
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={isCurrent ? "step" : undefined}
            >
              <div className="task-progress__milestone-title-row">
                <div className="task-progress__milestone-title">
                  {PHASE_LABELS[ms.pipeline_phase] ?? ms.subject}
                </div>
                {isCurrent ? (
                  <span className="task-progress__milestone-chip">进行中</span>
                ) : null}
              </div>
              {hasWorks ? (
                <ul className="task-progress__works">
                  {ms.works.map((w) => (
                    <li key={w.id} className="task-progress__work">
                      <span className="task-progress__work-title">{w.title}</span>
                      <span className="task-progress__work-status">{w.status}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
