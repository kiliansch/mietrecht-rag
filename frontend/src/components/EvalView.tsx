import { useEffect, useState } from "react";
import { getEvalResults, getEvalStatus, runEval } from "../api/client";
import type { AppConfig, EvalScores } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";

const METRIC_LABELS: Record<string, string> = {
  faithfulness: "Faithfulness",
  answer_relevancy: "Answer Relevance",
  context_precision: "Context Precision",
  context_recall: "Context Recall",
  hit_rate: "Hit-Rate@k",
  mrr: "MRR",
};

const AGENT_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"];
const RETRIEVAL_BASE_METRICS = ["context_precision", "context_recall"];
// Deterministic, judge-free retrieval metrics — shown only for collections that report
// them (case law carries a gold reference). See docs/parent_document_retrieval_eval.md.
const RETRIEVAL_EXTRA_METRICS = ["hit_rate", "mrr"];

function retrievalMetrics(scores: Record<string, number>): string[] {
  return [...RETRIEVAL_BASE_METRICS, ...RETRIEVAL_EXTRA_METRICS.filter((m) => m in scores)];
}

export function EvalView({ config }: { config: AppConfig }) {
  const t = useT();
  const [results, setResults] = useState<EvalScores | null>(null);
  const [status, setStatus] = useState<string>("idle");

  useEffect(() => {
    getEvalResults().then(setResults).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (status !== "running") return;
    const id = setInterval(async () => {
      try {
        const s = await getEvalStatus();
        setStatus(s.status);
        if (s.status === "done" && s.results) setResults(s.results);
      } catch {
        /* keep polling */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [status]);

  const start = async () => {
    setStatus("running");
    await runEval().catch(() => setStatus("error"));
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-primary">{t("eval.title")}</h2>
          <p className="mt-1 text-on-surface-variant">{t("eval.subtitle")}</p>
        </div>
        <button
          onClick={start}
          disabled={status === "running"}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          <Icon name="play_arrow" className="text-base" /> {t("eval.start")}
        </button>
      </div>

      {status === "running" && (
        <p className="flex items-center gap-2 rounded-lg bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
          <Icon name="progress_activity" className="animate-spin text-base" />
          {t("eval.running")}
        </p>
      )}
      {status === "error" && (
        <p className="rounded-lg bg-error-container px-4 py-3 text-sm text-on-error-container">
          {t("eval.error")}
        </p>
      )}

      {results && (
        <div className="grid gap-4 md:grid-cols-2">
          <ScoreTable
            title={t("eval.agentTitle")}
            scores={results.agent}
            metrics={AGENT_METRICS}
            thresholds={config.thresholds}
          />
          {Object.entries(results.retrieval).map(([collection, scores]) => (
            <ScoreTable
              key={collection}
              title={t("eval.retrievalTitle", { collection })}
              scores={scores}
              metrics={retrievalMetrics(scores)}
              thresholds={config.thresholds}
            />
          ))}
        </div>
      )}

      {results?.usage && (
        <p className="rounded-lg bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
          {t("eval.usage")}: {results.usage.input_tokens.toLocaleString("de-DE")}{" "}
          {t("eval.tokensIn")} · {results.usage.output_tokens.toLocaleString("de-DE")}{" "}
          {t("eval.tokensOut")} · ${results.usage.cost_usd.toFixed(4)}
        </p>
      )}

      {results?.retrieval?.case_law && (
        <p className="text-xs text-on-surface-variant">
          <Icon name="info" className="mr-1 align-middle text-sm" />
          {t("eval.caseLawNote")}
        </p>
      )}

      <p className="text-xs text-on-surface-variant">
        <Icon name="info" className="mr-1 align-middle text-sm" />
        {t("eval.naNote")}
      </p>
    </div>
  );
}

function ScoreTable({
  title,
  scores,
  metrics,
  thresholds,
}: {
  title: string;
  scores: Record<string, number>;
  metrics: string[];
  thresholds: Record<string, number>;
}) {
  const t = useT();
  return (
    <div className="overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-card">
      <div className="border-b border-outline-variant bg-surface-container-low px-4 py-3 font-semibold">{title}</div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-on-surface-variant">
            <th className="px-4 py-2 font-medium">{t("eval.colMetric")}</th>
            <th className="px-4 py-2 text-right font-medium">{t("eval.colScore")}</th>
            <th className="px-4 py-2 text-right font-medium">{t("eval.colThreshold")}</th>
            <th className="px-4 py-2 text-center font-medium">{t("eval.colStatus")}</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => {
            const score = scores[m];
            const threshold = thresholds[m];
            const isNaN = score == null || Number.isNaN(score);
            const ok = !isNaN && score >= threshold;
            return (
              <tr key={m} className="border-t border-outline-variant">
                <td className="px-4 py-2">{METRIC_LABELS[m] ?? m}</td>
                <td className="px-4 py-2 text-right tabular-nums">{isNaN ? "N/A" : score.toFixed(2)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-on-surface-variant">
                  {threshold?.toFixed(2) ?? "—"}
                </td>
                <td className="px-4 py-2 text-center">{isNaN ? "N/A" : ok ? "✅" : "⚠️"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
