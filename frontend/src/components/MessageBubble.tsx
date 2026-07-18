import { useState } from "react";
import type { ChatMessage } from "../api/types";
import { useT } from "../i18n";
import { ApprovalCard } from "./ApprovalCard";
import { GroundednessBadge } from "./GroundednessBadge";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";
import { SourceList } from "./SourceList";
import { ToolCallPanel } from "./ToolCallPanel";
import { FeedbackButtons } from "./FeedbackButtons";

interface Props {
  message: ChatMessage;
  question: string;
  onRate: (value: 1 | -1) => void;
  onApproval?: (decision: "approve" | "reject") => void;
  loading?: boolean;
}

export function MessageBubble({ message, question, onRate, onApproval, loading }: Props) {
  const isUser = message.role === "user";
  const [showSources, setShowSources] = useState(false);
  const t = useT();

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-on-primary shadow-card">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-prose space-y-3 rounded-2xl rounded-tl-sm border border-outline-variant bg-surface-container-lowest px-4 py-3 shadow-card">
        <div className="flex items-center gap-2 text-sm font-semibold text-primary">
          <Icon name="balance" className="text-base" /> {t("chat.aiName")}
        </div>

        {!!message.toolCalls?.length && <ToolCallPanel toolCalls={message.toolCalls} />}

        {message.content ? (
          <Markdown>{message.content}</Markdown>
        ) : message.pendingApproval ? null : (
          <span className="inline-flex items-center gap-2 text-on-surface-variant">
            <Icon name="progress_activity" className="animate-spin text-base" />
            {t("chat.analysing")}
          </span>
        )}

        {message.pendingApproval && onApproval && (
          <ApprovalCard
            approval={message.pendingApproval}
            disabled={!!loading}
            onDecision={onApproval}
          />
        )}

        {!loading && <GroundednessBadge message={message} />}

        {!!message.sources?.length && (
          <div className="rounded-lg border border-outline-variant bg-surface-container-low">
            <button
              onClick={() => setShowSources((s) => !s)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-on-surface-variant"
            >
              <Icon name="menu_book" className="text-base" /> {t("chat.sources")}
              <Icon name={showSources ? "expand_less" : "expand_more"} className="ml-auto text-base" />
            </button>
            {showSources && (
              <div className="border-t border-outline-variant px-3 py-2">
                <SourceList sources={message.sources} />
              </div>
            )}
          </div>
        )}

        {message.content && <FeedbackButtons message={message} question={question} onRate={onRate} />}
      </div>
    </div>
  );
}
