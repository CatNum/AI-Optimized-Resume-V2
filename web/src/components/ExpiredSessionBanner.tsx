type Props = {
  onNewSession: () => void;
};

export function ExpiredSessionBanner({ onNewSession }: Props) {
  return (
    <div className="mb-3 shrink-0 rounded border border-rose-800/60 bg-rose-950/50 px-3 py-3 text-sm text-rose-100">
      <p className="mb-2">
        此会话已过期，无法继续发送消息。请在左侧列表选择其它会话，或新建会话。
      </p>
      <button
        type="button"
        className="rounded bg-emerald-700 px-3 py-1 text-white hover:bg-emerald-600"
        onClick={() => void onNewSession()}
      >
        新建会话
      </button>
    </div>
  );
}
