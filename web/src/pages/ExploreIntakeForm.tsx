import { FormEvent, useMemo, useState } from "react";
import {
  emptyExploreIntake,
  submitExploreIntake,
  type ExploreIntakePayload,
} from "../lib/exploreIntake";

type Props = {
  sessionId: string;
  onClose: () => void;
  onSubmitted: () => void;
};

const inputClass =
  "w-full rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm";
const labelClass = "mb-1 block text-xs text-slate-400";

export function ExploreIntakeForm({ sessionId, onClose, onSubmitted }: Props) {
  const [form, setForm] = useState<ExploreIntakePayload>(() => emptyExploreIntake(sessionId));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => form.resume_text.trim().length >= 20, [form.resume_text]);

  function updateField<K extends keyof ExploreIntakePayload>(
    key: K,
    value: ExploreIntakePayload[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) {
      setError("请粘贴完整简历（至少 20 字）。");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await submitExploreIntake(form);
      onSubmitted();
      onClose();
    } catch {
      setError("提交失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <form
        onSubmit={handleSubmit}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900"
      >
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-lg font-semibold">初探信息表</h2>
          <p className="mt-1 text-sm text-slate-400">
            以完整简历为主。下方补充项可选；简历中已有的信息会自动识别，缺失项会在后续对话中向你确认。
          </p>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
          <label className="block">
            <span className={labelClass}>完整简历 *</span>
            <textarea
              className={`${inputClass} min-h-64 font-mono text-xs leading-relaxed`}
              placeholder="请粘贴简历全文（Markdown 或纯文本均可）"
              value={form.resume_text}
              onChange={(e) => updateField("resume_text", e.target.value)}
            />
          </label>

          <div>
            <p className="mb-2 text-sm font-medium text-emerald-300">补充信息（可选）</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className={labelClass}>工作年限</span>
                <input
                  className={inputClass}
                  placeholder="如：5 年"
                  value={form.years_of_experience}
                  onChange={(e) => updateField("years_of_experience", e.target.value)}
                />
              </label>
              <label className="block">
                <span className={labelClass}>目标岗位</span>
                <input
                  className={inputClass}
                  placeholder="如：后端工程师"
                  value={form.target_role}
                  onChange={(e) => updateField("target_role", e.target.value)}
                />
              </label>
              <label className="block">
                <span className={labelClass}>当前薪资</span>
                <input
                  className={inputClass}
                  placeholder="如：30k / 40万"
                  value={form.current_salary}
                  onChange={(e) => updateField("current_salary", e.target.value)}
                />
              </label>
              <label className="block">
                <span className={labelClass}>目标薪资</span>
                <input
                  className={inputClass}
                  placeholder="如：35k-45k"
                  value={form.target_salary}
                  onChange={(e) => updateField("target_salary", e.target.value)}
                />
              </label>
            </div>
          </div>

          {error ? <p className="text-sm text-amber-300">{error}</p> : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
          <button
            type="button"
            className="rounded px-4 py-2 text-sm text-slate-400"
            onClick={onClose}
            disabled={submitting}
          >
            稍后填写
          </button>
          <button
            type="submit"
            className="rounded bg-emerald-600 px-4 py-2 text-sm disabled:opacity-50"
            disabled={submitting || !canSubmit}
          >
            {submitting ? "提交中…" : "提交并继续初探"}
          </button>
        </div>
      </form>
    </div>
  );
}
