import {
  activityStatusLabel,
  type SessionActivity,
} from "../lib/sessionActivity";

export function TaskProgress({ activity }: { activity: SessionActivity | null }) {
  if (!activity?.items?.length) return null;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm">
      {activity.headline ? (
        <div className="mb-2 text-emerald-300/90">{activity.headline}</div>
      ) : (
        <div className="mb-2 font-medium text-slate-300">任务进度</div>
      )}
      <ul className="space-y-1">
        {activity.items.map((item) => (
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
