import { useEffect, useRef, useState } from "react";
import { validateInput } from "../api/client";
import type { ChatMessage, PendingApproval } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";
import { MessageBubble } from "./MessageBubble";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void;
  onRate: (index: number, value: 1 | -1) => void;
  onApproval?: (approval: PendingApproval, decision: "approve" | "reject") => void;
}

export function ChatView({ messages, loading, onSend, onRate, onApproval }: Props) {
  const [text, setText] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const t = useT();
  const examples = [t("chat.example1"), t("chat.example2"), t("chat.example3")];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    const { error } = await validateInput(trimmed);
    if (error) {
      setWarning(error);
      return;
    }
    setWarning(null);
    setText("");
    onSend(trimmed);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-8">
        {messages.length === 0 ? (
          <div className="mx-auto max-w-prose pt-10 text-center">
            <div className="mb-3 text-4xl">⚖️</div>
            <h2 className="text-xl font-semibold">{t("chat.welcome")}</h2>
            <p className="mt-2 text-on-surface-variant">{t("chat.welcomeSub")}</p>
            <div className="mt-6 grid gap-2 sm:grid-cols-1">
              {examples.map((q) => (
                <button
                  key={q}
                  onClick={() => submit(q)}
                  className="rounded-lg border border-outline-variant bg-surface-container-lowest px-4 py-3 text-left text-sm hover:bg-surface-container-low"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              message={m}
              question={i > 0 ? messages[i - 1].content : ""}
              onRate={(v) => onRate(i, v)}
              loading={loading}
              onApproval={
                m.pendingApproval && onApproval
                  ? (dec) => onApproval(m.pendingApproval as PendingApproval, dec)
                  : undefined
              }
            />
          ))
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-outline-variant bg-surface-container-lowest px-4 py-3 sm:px-8">
        {warning && <p className="mb-2 text-sm text-error">⚠️ {warning}</p>}
        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(text);
              }
            }}
            rows={1}
            maxLength={500}
            placeholder={t("chat.placeholder")}
            className="flex-1 resize-none rounded-lg border-outline-variant focus:border-primary focus:ring-primary"
          />
          <button
            onClick={() => submit(text)}
            disabled={loading || !text.trim()}
            className="rounded-lg bg-primary p-2.5 text-on-primary hover:opacity-90 disabled:opacity-40"
            title={t("chat.send")}
          >
            <Icon name="send" className="text-base" />
          </button>
        </div>
        <p className="mt-2 text-center text-xs text-on-surface-variant">
          {t("chat.disclaimer")}
        </p>
      </div>
    </div>
  );
}
