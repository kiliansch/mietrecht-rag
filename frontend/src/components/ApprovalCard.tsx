import { useState } from "react";
import type { PendingApproval } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";

const dateFmt = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE");
};

interface Props {
  approval: PendingApproval;
  disabled: boolean;
  onDecision: (decision: "approve" | "reject") => void;
}

/** Confirm/reject card for an agent-proposed action (HITL tool interrupt). */
export function ApprovalCard({ approval, disabled, onDecision }: Props) {
  const [answered, setAnswered] = useState(false);
  const t = useT();
  const args = approval.args as Record<string, string | undefined>;

  const decide = (decision: "approve" | "reject") => {
    if (answered || disabled) return;
    setAnswered(true);
    onDecision(decision);
  };

  return (
    <div className="rounded-lg border border-primary/40 bg-surface-container-low p-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-primary">
        <Icon name="pending_actions" className="text-base" />
        {approval.action === "create_deadline" && t("approval.createDeadline")}
        {approval.action === "save_draft" && t("approval.saveDraft")}
        {approval.action !== "create_deadline" &&
          approval.action !== "save_draft" &&
          t("approval.generic", { action: approval.action })}
      </p>

      {approval.action === "create_deadline" && (
        <div className="mt-2 text-sm">
          <p className="font-medium">{args.title}</p>
          <p className="text-on-surface-variant">{t("approval.dueOn", { date: dateFmt(args.due_date ?? "") })}</p>
          {args.note && <p className="mt-1 text-xs text-on-surface-variant">{args.note}</p>}
        </div>
      )}

      {approval.action === "save_draft" && (
        <div className="mt-2 text-sm">
          <p className="font-medium">{args.title}</p>
          {args.content && (
            <div className="mt-2 max-h-52 overflow-y-auto rounded-lg border border-outline-variant bg-surface-container-lowest p-2 text-sm">
              <Markdown>{args.content}</Markdown>
            </div>
          )}
        </div>
      )}

      <div className="mt-3 flex gap-2">
        <button
          onClick={() => decide("approve")}
          disabled={answered || disabled}
          className="flex items-center gap-1 rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-40"
        >
          <Icon name="check" className="text-base" /> {t("approval.confirm")}
        </button>
        <button
          onClick={() => decide("reject")}
          disabled={answered || disabled}
          className="flex items-center gap-1 rounded-lg border border-outline-variant px-4 py-1.5 text-sm hover:bg-surface-container disabled:opacity-40"
        >
          <Icon name="close" className="text-base" /> {t("approval.reject")}
        </button>
      </div>
    </div>
  );
}
