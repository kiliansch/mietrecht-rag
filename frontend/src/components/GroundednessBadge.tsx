import type { ChatMessage } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";

// The exact grounding-fallback sentence the agent emits when nothing relevant was found.
const NO_INFO = "Diese Information ist in den verfügbaren Quellen nicht enthalten";

/**
 * Per-answer groundedness signal derived from the citations the agent actually
 * produced — how many primary sources back the answer, split into statutes vs.
 * case law. Makes "is this answer supported?" legible without an extra LLM call.
 */
export function GroundednessBadge({ message }: { message: ChatMessage }) {
  const t = useT();
  if (!message.content) return null;

  if (message.content.includes(NO_INFO)) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-on-surface-variant">
        <Icon name="info" className="text-sm" /> {t("badge.none")}
      </p>
    );
  }

  // De-dupe by URL (else header), then split by collection.
  const seen = new Set<string>();
  let statutes = 0;
  let caseLaw = 0;
  for (const s of message.sources ?? []) {
    const key = s.url || s.header;
    if (seen.has(key)) continue;
    seen.add(key);
    if (s.source === "case_law") caseLaw++;
    else statutes++;
  }
  const total = statutes + caseLaw;
  if (total === 0) return null; // e.g. a pure calculator answer — don't mislabel it

  const parts: string[] = [];
  if (statutes)
    parts.push(`${statutes} ${t(statutes === 1 ? "badge.statute.one" : "badge.statute.other")}`);
  if (caseLaw) parts.push(`${caseLaw} ${t(caseLaw === 1 ? "badge.ruling.one" : "badge.ruling.other")}`);

  return (
    <p className="flex items-center gap-1.5 text-xs font-medium text-success">
      <Icon name="verified" className="text-sm" /> {t("badge.groundedPrefix")} {parts.join(" · ")}
    </p>
  );
}
