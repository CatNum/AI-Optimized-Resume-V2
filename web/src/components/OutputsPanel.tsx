import { useCallback, useEffect, useState } from "react";

type OutputEntry = { path: string; optimization_level?: string };

type Props = {
  refreshTrigger?: number;
};

function displayName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function openHref(path: string): string {
  return `/v1/outputs/view?path=${encodeURIComponent(path)}`;
}

export function OutputsPanel({ refreshTrigger = 0 }: Props) {
  const [items, setItems] = useState<OutputEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/v1/outputs");
      if (!r.ok) throw new Error(`加载失败 (${r.status})`);
      const data = await r.json();
      setItems(data.outputs_index || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshTrigger]);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-l border-slate-800 bg-slate-950">
      <div className="border-b border-slate-800 px-3 py-3">
        <h2 className="font-medium text-slate-100">简历产物</h2>
        <p className="mt-1 text-xs text-slate-500">优化后的 HTML 简历</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {error ? (
          <p className="px-2 py-4 text-sm text-rose-300">{error}</p>
        ) : loading && items.length === 0 ? (
          <p className="px-2 py-4 text-sm text-slate-500">加载中…</p>
        ) : items.length === 0 ? (
          <p className="px-2 py-4 text-sm text-slate-500">暂无简历产物</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li key={item.path}>
                <div className="rounded-lg border border-transparent px-3 py-2 hover:border-slate-700 hover:bg-slate-900/80">
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0 flex-1 truncate text-sm text-slate-100" title={item.path}>
                      {displayName(item.path)}
                    </span>
                    {item.optimization_level ? (
                      <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                        {item.optimization_level}
                      </span>
                    ) : null}
                  </div>
                  <a
                    className="mt-2 inline-block text-xs text-emerald-400 hover:text-emerald-300"
                    href={openHref(item.path)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开
                  </a>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
