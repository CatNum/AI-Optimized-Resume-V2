import { useCallback, useState } from "react";
import type { FileRefAttachment } from "../lib/chatAttachments";
import type { ContextUsage } from "../lib/contextUsage";

type ChatHandlers = {
  onSession: (sessionId: string) => void;
  onToken: (delta: string) => void;
  onHistoryNotice: (payload: ContextUsage) => void;
  onExploreIntake: () => void;
  onDone: (payload: { context_usage?: ContextUsage }) => void;
  onError: (message: string) => void;
};

export type ChatRequestOptions = {
  market_action?: "start_confirmed_plan";
};

export function useChatSSE() {
  const [loading, setLoading] = useState(false);

  const sendMessage = useCallback(
    async (
      message: string,
      sessionId: string | null,
      handlers: ChatHandlers,
      attachments?: FileRefAttachment[],
      options?: ChatRequestOptions,
    ) => {
      setLoading(true);
      try {
        const payload: {
          session_id: string | null;
          message: string;
          attachments?: FileRefAttachment[];
          market_action?: "start_confirmed_plan";
        } = { session_id: sessionId, message };
        if (attachments && attachments.length > 0) {
          payload.attachments = attachments;
        }
        if (options?.market_action) payload.market_action = options.market_action;
        const response = await fetch("/v1/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify(payload),
        });

        if (response.status === 409) {
          const payload = await response.json().catch(() => null);
          handlers.onError(payload?.detail?.code || "chat_in_progress");
          return;
        }
        if (!response.ok || !response.body) {
          handlers.onError(`HTTP ${response.status}`);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";
          for (const part of parts) {
            const lines = part.split("\n");
            const eventLine = lines.find((l) => l.startsWith("event:"));
            const dataLine = lines.find((l) => l.startsWith("data:"));
            if (!eventLine || !dataLine) continue;
            const event = eventLine.replace("event:", "").trim();
            const data = JSON.parse(dataLine.replace("data:", "").trim());
            if (event === "session") handlers.onSession(data.session_id);
            if (event === "token") handlers.onToken(data.delta);
            if (event === "history_notice") handlers.onHistoryNotice(data);
            if (event === "explore_intake") handlers.onExploreIntake();
            if (event === "done") handlers.onDone(data);
            if (event === "error") handlers.onError(data.message);
          }
        }
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return { sendMessage, loading };
}
