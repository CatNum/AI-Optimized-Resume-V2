import { FormEvent, useState } from "react";

export function OnboardingForm({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [city, setCity] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    await fetch("/v1/profile/onboarding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        basic: { name },
        intent: { target_city: city },
      }),
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-md space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-6"
      >
        <h2 className="text-lg font-semibold">职业建档</h2>
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
          placeholder="姓名"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
          placeholder="目标城市"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
        <button className="rounded bg-emerald-600 px-4 py-2" type="submit">
          提交
        </button>
      </form>
    </div>
  );
}
