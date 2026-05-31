type Task = {
  id: string;
  title: string;
  status: string;
};

export function TaskProgress({ tasks }: { tasks: Task[] }) {
  if (!tasks.length) return null;
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3 text-sm">
      <div className="mb-2 font-medium text-slate-300">任务进度</div>
      <ul className="space-y-1">
        {tasks.map((task) => (
          <li key={task.id} className="flex justify-between text-slate-400">
            <span>{task.title || task.id}</span>
            <span>{task.status}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
