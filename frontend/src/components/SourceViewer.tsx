import { useEffect, useState } from "react";
import { getSource } from "../api/client";
import type { Source, SourceDetail } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";

const cleanUrl = (url: string) => url.replace(/\/+$/, "");

/**
 * Modal that shows the full primary source (statute § or court decision) behind a
 * citation, fetched from our own corpus so the user can verify an answer without
 * leaving the app. An external link to Open Legal Data is offered as a fallback.
 */
export function SourceViewer({ source, onClose }: { source: Source; onClose: () => void }) {
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const t = useT();

  useEffect(() => {
    let alive = true;
    getSource(source.source, source.url)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [source.source, source.url]);

  // Close on Escape for keyboard users.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start gap-3 border-b border-outline-variant px-5 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase text-on-surface-variant">
              {source.source === "case_law" ? t("source.case_law") : t("source.statutes")}
            </p>
            <p className="truncate font-semibold">{detail?.title ?? source.header}</p>
          </div>
          {source.url && (
            <a
              href={cleanUrl(source.url)}
              target="_blank"
              rel="noreferrer"
              title={t("source.openExternal")}
              className="text-on-surface-variant hover:text-primary"
            >
              <Icon name="open_in_new" className="text-base" />
            </a>
          )}
          <button onClick={onClose} title={t("source.close")} className="text-on-surface-variant hover:text-primary">
            <Icon name="close" className="text-base" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {error && <p className="text-sm text-error">❌ {error}</p>}
          {!error && !detail && <p className="text-sm text-on-surface-variant">{t("source.loading")}</p>}
          {detail?.blocks.map((b, i) => (
            <div key={i} className="mb-4">
              {b.heading && (
                <p className="mb-1 text-xs font-semibold uppercase text-on-surface-variant">{b.heading}</p>
              )}
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{b.content}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
