import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type OutputEntry = { path: string; optimization_level?: string };

export function OutputsPage() {
  const [items, setItems] = useState<OutputEntry[]>([]);

  useEffect(() => {
    fetch("/v1/outputs")
      .then((r) => r.json())
      .then((data) => setItems(data.outputs_index || []));
  }, []);

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">简历产物</h1>
        <Link className="text-emerald-400" to="/">
          返回对话
        </Link>
      </div>
      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item.path}
            className="flex items-center justify-between rounded border border-slate-800 p-3"
          >
            <span>{item.path}</span>
            <a className="text-emerald-400" href={`/${item.path}`} target="_blank">
              打开
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
