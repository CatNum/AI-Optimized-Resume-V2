import {
  contextUsageTooltip,
  type ContextUsage,
  usageDisplayPercent,
} from "../lib/contextUsage";

type Props = {
  usage: ContextUsage | null;
};

export function ContextUsageIndicator({ usage }: Props) {
  if (!usage) return null;

  const percent = usageDisplayPercent(usage);
  const warn = usage.recommend_new_session || usage.trimmed;

  return (
    <span
      className={`cursor-help rounded px-2 py-0.5 text-xs tabular-nums ${
        warn
          ? "border border-amber-700/50 bg-amber-950/40 text-amber-200"
          : "border border-slate-700 bg-slate-900/60 text-slate-400"
      }`}
      title={contextUsageTooltip(usage)}
    >
      上下文 {percent}%
    </span>
  );
}
