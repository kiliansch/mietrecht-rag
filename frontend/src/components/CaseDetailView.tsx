import { useCallback, useEffect, useRef, useState } from "react";
import {
  analyseCaseDocument,
  createDeadline,
  deleteCaseDocument,
  deleteDeadline,
  getCase,
  getCaseDocument,
  reviewCaseContract,
  setDeadlineStatus,
  uploadCaseDocument,
} from "../api/client";
import { parseSSE } from "../api/sse";
import type { CaseDetail, CaseDocument, Deadline, DocumentKind, Finding } from "../api/types";
import { useChat } from "../state/useChat";
import { useWorkspace } from "../state/workspace";
import { useT } from "../i18n";
import { ChatView } from "./ChatView";
import { ClauseFindingCard } from "./ClauseFindingCard";
import { download, draftToPDF } from "./ExportMenu";
import { Icon } from "./Icon";
import { Markdown } from "./Markdown";

const dateFmt = (iso: string) => new Date(iso).toLocaleDateString("de-DE");
const today = () => new Date().toISOString().slice(0, 10);
const isOverdue = (d: Deadline) => d.status === "open" && d.due_date < today();

// Icon per document kind; the label comes from i18n (`docs.<kind>`).
const KIND_META: Record<DocumentKind, { icon: string }> = {
  contract: { icon: "description" },
  letter: { icon: "mail" },
  draft: { icon: "edit_note" },
};

interface Props {
  caseId: string;
  onBack: () => void;
}

export function CaseDetailView({ caseId, onBack }: Props) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chat = useChat(caseId);
  const { refreshProfile, refreshCases } = useWorkspace();
  const t = useT();
  // The document whose analysis is in flight: if the turn pauses on an approval,
  // the resume passes this id so the final answer still lands on the document.
  const analysingDocId = useRef<string | null>(null);

  const reload = useCallback(() => {
    getCase(caseId)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [caseId]);

  // Any change here (documents, deadlines, extracted facts) can move what the
  // sidebar shows — reload the case AND the shared workspace (facts + Akten).
  const reloadAll = useCallback(() => {
    reload();
    refreshProfile();
    refreshCases();
  }, [reload, refreshProfile, refreshCases]);

  useEffect(reload, [reload]);

  // Letter analysis streams into the case chat, then persists → refresh the panel.
  const analyse = (doc: CaseDocument) => {
    analysingDocId.current = doc.id;
    chat
      .streamTurn(t("caseDetail.analyseRequest", { title: doc.title }), (signal) =>
        analyseCaseDocument(caseId, doc.id, signal),
      )
      .then(reloadAll);
  };

  if (error) {
    return (
      <div className="p-8 text-center">
        <p className="text-error">❌ {error}</p>
        <button onClick={onBack} className="mt-4 text-sm text-primary hover:underline">
          {t("caseDetail.backToCases")}
        </button>
      </div>
    );
  }
  if (!detail) {
    return <div className="p-8 text-center text-on-surface-variant">{t("app.loading")}</div>;
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-outline-variant bg-surface-container-lowest px-4 py-2.5">
        <button onClick={onBack} title={t("caseDetail.back")} className="text-on-surface-variant hover:text-primary">
          <Icon name="arrow_back" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">📁 {detail.title}</p>
          <p className="text-xs text-on-surface-variant">
            {t("caseDetail.subtitle", { date: dateFmt(detail.created_at) })}
          </p>
        </div>
      </header>

      {/* Body: chat + side panel */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="min-h-0 min-w-0 flex-1">
          <ChatView
            messages={chat.messages}
            loading={chat.loading}
            onSend={(t) => {
              analysingDocId.current = null; // new input supersedes the analysis turn
              chat.send(t).then(reloadAll);
            }}
            onRate={chat.setFeedback}
            // Approving may create a deadline/draft → refresh the side panel + sidebar.
            onApproval={(a, dec) =>
              chat
                .respondApproval(a, dec, { documentId: analysingDocId.current ?? undefined })
                .then(reloadAll)
            }
          />
        </div>

        <aside className="max-h-72 space-y-5 overflow-y-auto border-t border-outline-variant bg-surface-container-lowest p-4 lg:max-h-none lg:w-96 lg:border-l lg:border-t-0">
          <DeadlinePanel caseId={caseId} deadlines={detail.deadlines} onChange={reloadAll} />
          <hr className="border-outline-variant" />
          <DocumentPanel
            caseId={caseId}
            documents={detail.documents}
            busy={chat.loading}
            onAnalyse={analyse}
            onChange={reloadAll}
          />
        </aside>
      </div>
    </div>
  );
}

// --- Deadlines (Fristen) ---------------------------------------------------------------

function DeadlinePanel({
  caseId,
  deadlines,
  onChange,
}: {
  caseId: string;
  deadlines: Deadline[];
  onChange: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const t = useT();

  const overdueCount = deadlines.filter(isOverdue).length;

  const add = async () => {
    if (!title.trim() || !due) return;
    await createDeadline(caseId, { title: title.trim(), due_date: due }).catch(() => undefined);
    setTitle("");
    setDue("");
    setAdding(false);
    onChange();
  };

  const toggle = async (d: Deadline) => {
    await setDeadlineStatus(caseId, d.id, d.status === "done" ? "open" : "done").catch(
      () => undefined,
    );
    onChange();
  };

  const remove = async (d: Deadline) => {
    await deleteDeadline(caseId, d.id).catch(() => undefined);
    onChange();
  };

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center justify-between">
        <p className="font-semibold">
          {t("deadlines.title")}
          {overdueCount > 0 && (
            <span className="ml-2 rounded-full bg-error-container px-2 py-0.5 text-xs font-medium text-on-error-container">
              {t("deadlines.overdueBadge", { n: overdueCount })}
            </span>
          )}
        </p>
        <button
          onClick={() => setAdding((a) => !a)}
          className="text-xs text-primary hover:underline"
        >
          {adding ? t("deadlines.cancel") : t("deadlines.add")}
        </button>
      </div>

      {adding && (
        <div className="space-y-2 rounded-lg border border-outline-variant p-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("deadlines.titlePlaceholder")}
            className="w-full rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
          />
          <div className="flex gap-2">
            <input
              type="date"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              className="flex-1 rounded-lg border-outline-variant text-sm focus:border-primary focus:ring-primary"
            />
            <button
              onClick={add}
              disabled={!title.trim() || !due}
              className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:opacity-90 disabled:opacity-40"
            >
              {t("deadlines.create")}
            </button>
          </div>
        </div>
      )}

      {deadlines.length === 0 && !adding && (
        <p className="text-on-surface-variant">{t("deadlines.empty")}</p>
      )}

      <ul className="space-y-1.5">
        {deadlines.map((d) => (
          <li
            key={d.id}
            className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${
              isOverdue(d)
                ? "border-error/40 bg-error-container/50"
                : "border-outline-variant bg-surface-container-lowest"
            }`}
          >
            <input
              type="checkbox"
              checked={d.status === "done"}
              onChange={() => toggle(d)}
              title={d.status === "done" ? t("deadlines.reopen") : t("deadlines.markDone")}
              className="mt-0.5 rounded border-outline-variant text-primary focus:ring-primary"
            />
            <div className="min-w-0 flex-1">
              <p className={d.status === "done" ? "line-through opacity-60" : ""}>{d.title}</p>
              <p className="text-xs text-on-surface-variant">
                {isOverdue(d) && <span className="font-medium text-error">{t("deadlines.overduePrefix")}</span>}
                {dateFmt(d.due_date)}
                {d.created_by === "agent" && t("deadlines.byAssistant")}
              </p>
              {d.note && <p className="mt-0.5 text-xs text-on-surface-variant">{d.note}</p>}
            </div>
            <button
              onClick={() => remove(d)}
              title={t("deadlines.delete")}
              className="text-on-surface-variant hover:text-error"
            >
              <Icon name="close" className="text-sm" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Documents ---------------------------------------------------------------------------

function DocumentPanel({
  caseId,
  documents,
  busy,
  onAnalyse,
  onChange,
}: {
  caseId: string;
  documents: CaseDocument[];
  busy: boolean;
  onAnalyse: (doc: CaseDocument) => void;
  onChange: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadInfo, setUploadInfo] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const kindRef = useRef<DocumentKind>("letter");
  const t = useT();

  const pick = (kind: DocumentKind) => {
    kindRef.current = kind;
    fileRef.current?.click();
  };

  const onFile = async (file: File) => {
    const kind = kindRef.current;
    setUploading(true);
    setUploadError(null);
    setUploadInfo(null);
    try {
      const doc = await uploadCaseDocument(caseId, file, kind);
      // Make the contract-facts extraction legible instead of silent: say what
      // landed in "Mein Mietfall" (or that nothing was recognised automatically).
      if (kind === "contract") {
        const count = Object.keys(doc.extracted_facts ?? {}).length;
        setUploadInfo(
          count > 0
            ? t(count === 1 ? "docs.factsImported.one" : "docs.factsImported.other", { n: count })
            : t("docs.noFactsRecognised"),
        );
      }
      onChange();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-2 text-sm">
      <p className="font-semibold">{t("docs.title")}</p>

      <div className="flex gap-2">
        <button
          onClick={() => pick("letter")}
          disabled={uploading}
          className="flex-1 rounded-lg border border-outline-variant px-2 py-1.5 text-xs hover:bg-surface-container-low disabled:opacity-50"
        >
          <Icon name="mail" className="mr-1 align-middle text-sm" /> {t("docs.letter")}
        </button>
        <button
          onClick={() => pick("contract")}
          disabled={uploading}
          className="flex-1 rounded-lg border border-outline-variant px-2 py-1.5 text-xs hover:bg-surface-container-low disabled:opacity-50"
        >
          <Icon name="description" className="mr-1 align-middle text-sm" /> {t("docs.contract")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
      </div>
      {uploading && (
        <p className="flex items-center gap-2 text-xs text-on-surface-variant">
          <Icon name="progress_activity" className="animate-spin text-sm" /> {t("docs.reading")}
        </p>
      )}
      {uploadError && <p className="text-xs text-error">❌ {uploadError}</p>}
      {uploadInfo && !uploading && <p className="text-xs text-on-surface-variant">ℹ️ {uploadInfo}</p>}

      {documents.length === 0 && !uploading && (
        <p className="text-on-surface-variant">{t("docs.empty")}</p>
      )}

      <ul className="space-y-1.5">
        {documents.map((doc) => (
          <DocumentEntry
            key={doc.id}
            caseId={caseId}
            doc={doc}
            busy={busy || uploading}
            onAnalyse={onAnalyse}
            onChange={onChange}
          />
        ))}
      </ul>
    </div>
  );
}

function DocumentEntry({
  caseId,
  doc,
  busy,
  onAnalyse,
  onChange,
}: {
  caseId: string;
  doc: CaseDocument;
  busy: boolean;
  onAnalyse: (doc: CaseDocument) => void;
  onChange: () => void;
}) {
  const meta = KIND_META[doc.kind];
  const t = useT();
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  // Contract-review streaming state (renders inside this entry).
  const [reviewing, setReviewing] = useState(false);
  const [progress, setProgress] = useState<{ index: number; total: number; heading: string } | null>(null);
  const [liveFindings, setLiveFindings] = useState<Finding[]>([]);

  const toggleOpen = async () => {
    const next = !open;
    setOpen(next);
    if (next && content === null) {
      const full = await getCaseDocument(caseId, doc.id).catch(() => null);
      setContent(full?.content ?? "");
    }
  };

  const remove = async () => {
    if (!window.confirm(t("docs.deleteConfirm", { title: doc.title }))) return;
    await deleteCaseDocument(caseId, doc.id).catch(() => undefined);
    onChange();
  };

  const review = async () => {
    setReviewing(true);
    setLiveFindings([]);
    try {
      const res = await reviewCaseContract(caseId, doc.id);
      if (!res.ok || !res.body) throw new Error(`Fehler ${res.status}`);
      for await (const frame of parseSSE(res.body)) {
        const data = frame.data ? JSON.parse(frame.data) : {};
        if (frame.event === "progress") setProgress(data);
        else if (frame.event === "finding") setLiveFindings((prev) => [...prev, data as Finding]);
        else if (frame.event === "done") break;
      }
    } catch {
      /* surfaced via persisted analysis refresh below */
    } finally {
      setReviewing(false);
      setProgress(null);
      onChange();
    }
  };

  const analysis = doc.analysis;
  const contractSummary =
    analysis && typeof analysis.summary === "object" ? analysis.summary : null;
  const letterSummary = analysis && typeof analysis.summary === "string" ? analysis.summary : null;
  const findings: Finding[] =
    liveFindings.length > 0 ? liveFindings : analysis && "findings" in analysis ? analysis.findings : [];

  return (
    <li className="rounded-lg border border-outline-variant bg-surface-container-lowest">
      <div className="flex items-center gap-2 px-3 py-2">
        <Icon name={meta.icon} className="text-base text-primary" />
        <button onClick={toggleOpen} className="min-w-0 flex-1 text-left">
          <p className="truncate">{doc.title}</p>
          <p className="text-xs text-on-surface-variant">
            {t(`docs.${doc.kind}`)} · {dateFmt(doc.created_at)}
            {analysis ? t("docs.analysedSuffix") : ""}
          </p>
        </button>
        {doc.kind === "letter" && (
          <button
            onClick={() => onAnalyse(doc)}
            disabled={busy}
            title={t("docs.analyseTitle")}
            className="rounded-lg border border-outline-variant px-2 py-1 text-xs text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            {t("docs.analyse")}
          </button>
        )}
        {doc.kind === "contract" && (
          <button
            onClick={review}
            disabled={busy || reviewing}
            title={t("docs.reviewTitle")}
            className="rounded-lg border border-outline-variant px-2 py-1 text-xs text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            {reviewing ? t("docs.reviewing") : t("docs.review")}
          </button>
        )}
        <button onClick={remove} title={t("docs.delete")} className="text-on-surface-variant hover:text-error">
          <Icon name="close" className="text-sm" />
        </button>
      </div>

      {(reviewing || progress) && (
        <div className="px-3 pb-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: progress ? `${((progress.index + 1) / progress.total) * 100}%` : "5%" }}
            />
          </div>
          <p className="mt-1 text-xs text-on-surface-variant">
            {progress
              ? t("docs.clauseProgress", {
                  i: progress.index + 1,
                  n: progress.total,
                  heading: progress.heading,
                })
              : t("docs.checkingClauses")}
          </p>
        </div>
      )}

      {contractSummary && !reviewing && (
        <p className="px-3 pb-2 text-xs text-on-surface-variant">
          ✅ {contractSummary.wirksam ?? 0} · ⚠️ {contractSummary.bedenklich ?? 0} · ❌{" "}
          {contractSummary.unwirksam ?? 0}
        </p>
      )}

      {open && (
        <div className="space-y-3 border-t border-outline-variant px-3 py-3">
          {letterSummary && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase text-on-surface-variant">{t("docs.analysisLabel")}</p>
              <div className="text-sm">
                <Markdown>{letterSummary}</Markdown>
              </div>
            </div>
          )}
          {findings.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase text-on-surface-variant">{t("docs.clauseCheck")}</p>
              {findings.map((f, i) => (
                <ClauseFindingCard key={i} finding={f} />
              ))}
            </div>
          )}
          <div>
            <p className="mb-1 text-xs font-semibold uppercase text-on-surface-variant">{t("docs.documentText")}</p>
            {content === null ? (
              <p className="text-xs text-on-surface-variant">{t("app.loading")}</p>
            ) : doc.kind === "draft" ? (
              <div className="space-y-2">
                <div className="text-sm">
                  <Markdown>{content}</Markdown>
                </div>
                <button
                  onClick={() => download(draftToPDF(doc.title, content), `${doc.title}.pdf`, "application/pdf")}
                  className="flex items-center gap-1 rounded-lg border border-outline-variant px-3 py-1.5 text-xs text-primary hover:bg-surface-container-low"
                >
                  <Icon name="download" className="text-sm" /> {t("docs.exportPdf")}
                </button>
              </div>
            ) : (
              <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-lg bg-surface-container-low p-2 text-xs">
                {content}
              </pre>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
