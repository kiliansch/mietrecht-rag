import { useState } from "react";
import type { Finding } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";
import { SourceList } from "./SourceList";
import { VERDICT_META } from "./verdict";

export function ClauseFindingCard({ finding }: { finding: Finding }) {
  const meta = VERDICT_META[finding.verdict];
  const t = useT();
  const [open, setOpen] = useState(finding.verdict !== "wirksam");

  return (
    <div className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest shadow-card">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${meta.chip}`}>
          {meta.icon} {t(`verdict.${finding.verdict}`)}
        </span>
        <span className="font-medium text-on-surface">{finding.heading}</span>
        <Icon name={open ? "expand_less" : "expand_more"} className="ml-auto text-base text-on-surface-variant" />
      </button>
      {open && (
        <div className="space-y-3 border-t border-outline-variant px-4 py-3 text-sm">
          <div>
            <p className="mb-1 font-semibold">{t("docs.reasoning")}</p>
            <Markdown>{finding.reasoning}</Markdown>
          </div>
          {!!finding.sources.length && (
            <div className="rounded-lg border border-outline-variant bg-surface-container-low p-3">
              <p className="mb-1 font-medium text-on-surface-variant">{t("docs.sources")}</p>
              <SourceList sources={finding.sources} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
