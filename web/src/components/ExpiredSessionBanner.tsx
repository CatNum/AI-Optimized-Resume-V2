type Props = {
  onSwitchSession: () => void;
  onNewSession: () => void;
};

export function ExpiredSessionBanner({ onSwitchSession, onNewSession }: Props) {
  return (
    <div className="mb-3 shrink-0 rounded border border-rose-800/60 bg-rose-950/50 px-3 py-3 text-sm text-rose-100">
      <p className="mb-2">此会话已过期，无法继续发送消息。对话记录仍保留，可切换其它会话或新建会话。</p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded border border-slate-600 px-3 py-1 text-slate-200 hover:bg-slate-800"
          onClick={onSwitchSession}
        >
          切换会话
        </button>
        <button
          type="button"
          className="rounded bg-emerald-700 px-3 py-1 text-white hover:bg-emerald-600"
          onClick={() => void onNewSession()}
        >
          新建会话
        </button>
      </div>
    </div>
  );
}
