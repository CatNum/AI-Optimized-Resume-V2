export function ThinkingIndicator() {
  return (
    <div
      className="mr-12 flex items-center gap-3 rounded-lg bg-slate-800 px-4 py-3 text-sm text-slate-400"
      role="status"
      aria-live="polite"
    >
      <span className="flex gap-1.5" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="thinking-dot h-2 w-2 rounded-full bg-emerald-400/90"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </span>
      <span>思考中…</span>
    </div>
  );
}
