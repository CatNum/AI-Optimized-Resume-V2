import { useEffect, useState } from "react";

type Props = {
  active: boolean;
};

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest > 0 ? `${minutes}m ${rest}s` : `${minutes}m`;
}

export function ThinkingIndicator({ active }: Props) {
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsedSec(0);
      return;
    }
    const startedAt = Date.now();
    setElapsedSec(0);
    const timer = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(timer);
  }, [active]);

  if (!active) return null;

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
      <span>
        思考中… <span className="tabular-nums text-slate-500">{formatElapsed(elapsedSec)}</span>
      </span>
    </div>
  );
}
