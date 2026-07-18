import { useState } from "react";
import { createCase, deleteCase } from "../api/client";
import type { CaseSummary } from "../api/types";
import { useWorkspace } from "../state/workspace";
import { useT } from "../i18n";
import { Icon } from "./Icon";

const dateFmt = (iso: string) => new Date(iso).toLocaleDateString("de-DE");
const isOverdue = (iso: string) => iso < new Date().toISOString().slice(0, 10);

export function CaseListView({ onOpen }: { onOpen: (caseId: string) => void }) {
  const { cases, refreshCases } = useWorkspace();
  const t = useT();
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    if (!title.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createCase(title.trim());
      setTitle("");
      refreshCases(); // sidebar + list reflect the new Akte immediately
      onOpen(created.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (c: CaseSummary) => {
    if (!window.confirm(t("cases.deleteConfirm", { title: c.title }))) return;
    await deleteCase(c.id).catch(() => undefined);
    refreshCases();
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-8">
      <div>
        <h2 className="text-2xl font-bold text-primary">{t("cases.title")}</h2>
        <p className="mt-1 text-on-surface-variant">{t("cases.subtitle")}</p>
      </div>

      {error && (
        <p className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">❌ {error}</p>
      )}

      {/* Create */}
      <div className="flex gap-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && create()}
          placeholder={t("cases.newPlaceholder")}
          className="flex-1 rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
        />
        <button
          onClick={create}
          disabled={!title.trim() || busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-40"
        >
          <Icon name="create_new_folder" className="text-base" /> {t("cases.new")}
        </button>
      </div>

      {/* Cards */}
      {cases.length === 0 ? (
        <div className="rounded-xl border border-dashed border-outline-variant p-10 text-center text-on-surface-variant">
          <div className="mb-2 text-3xl">📁</div>
          {t("cases.empty")}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {cases.map((c) => (
            <div
              key={c.id}
              onClick={() => onOpen(c.id)}
              className="cursor-pointer rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-card transition hover:bg-surface-container-low"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="font-semibold">📁 {c.title}</p>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(c);
                  }}
                  title={t("cases.deleteTitle")}
                  className="text-on-surface-variant hover:text-error"
                >
                  <Icon name="delete" className="text-base" />
                </button>
              </div>
              <p className="mt-1 text-xs text-on-surface-variant">
                {t("cases.createdOn", { date: dateFmt(c.created_at) })} · {c.document_count}{" "}
                {t(c.document_count === 1 ? "cases.doc.one" : "cases.doc.other")}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                {c.next_due ? (
                  <span
                    className={`rounded-full px-2 py-0.5 ${
                      isOverdue(c.next_due)
                        ? "bg-error-container font-medium text-on-error-container"
                        : "bg-warning-container/50 text-on-warning-container"
                    }`}
                  >
                    ⏰ {isOverdue(c.next_due) ? t("cases.overdue") : t("cases.nextDeadline")}
                    {dateFmt(c.next_due)}
                  </span>
                ) : (
                  <span className="rounded-full bg-surface-container px-2 py-0.5 text-on-surface-variant">
                    {t("cases.noDeadlines")}
                  </span>
                )}
                {c.open_deadlines > 0 && (
                  <span className="rounded-full bg-surface-container px-2 py-0.5 text-on-surface-variant">
                    {t(c.open_deadlines === 1 ? "cases.openDeadlines.one" : "cases.openDeadlines.other", {
                      n: c.open_deadlines,
                    })}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
