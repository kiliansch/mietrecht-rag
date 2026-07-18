import { useState } from "react";
import { postFeedback } from "../api/client";
import { useSession } from "../state/session";
import type { ChatMessage } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";

interface Props {
  message: ChatMessage;
  question: string;
  onRate: (value: 1 | -1) => void;
}

export function FeedbackButtons({ message, question, onRate }: Props) {
  const { threadId } = useSession();
  const t = useT();
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState("");

  if (message.feedback === 1)
    return <p className="text-xs text-on-surface-variant">{t("feedback.ratedHelpful")}</p>;
  if (message.feedback === -1)
    return <p className="text-xs text-on-surface-variant">{t("feedback.ratedNot")}</p>;

  const submit = (rating: 1 | -1, text = "") => {
    onRate(rating);
    postFeedback({
      thread_id: threadId,
      question,
      answer: message.content,
      rating,
      comment: text,
    }).catch(() => undefined);
  };

  return (
    <div className="mt-1 space-y-2">
      <div className="flex gap-1">
        <button
          onClick={() => submit(1)}
          title={t("feedback.helpful")}
          className="rounded-lg border border-outline-variant px-2 py-1 text-sm hover:bg-surface-container"
        >
          <Icon name="thumb_up" className="text-base" />
        </button>
        <button
          onClick={() => setCommenting(true)}
          title={t("feedback.notHelpful")}
          className="rounded-lg border border-outline-variant px-2 py-1 text-sm hover:bg-surface-container"
        >
          <Icon name="thumb_down" className="text-base" />
        </button>
      </div>
      {commenting && (
        <div className="space-y-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={500}
            placeholder={t("feedback.commentPlaceholder")}
            className="w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            rows={2}
          />
          <button
            onClick={() => submit(-1, comment)}
            className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-on-primary hover:opacity-90"
          >
            {t("feedback.submit")}
          </button>
        </div>
      )}
    </div>
  );
}
