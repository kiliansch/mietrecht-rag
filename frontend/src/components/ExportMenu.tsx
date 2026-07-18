import { useState } from "react";
import { jsPDF } from "jspdf";
import type { ChatMessage } from "../api/types";
import { useT, type TFunc } from "../i18n";
import { PDF_FONT_FAMILY, registerPdfFont } from "../pdfFont";

type Format = "JSON" | "CSV" | "PDF";

export function download(data: Blob | string, filename: string, mime: string) {
  const blob = typeof data === "string" ? new Blob([data], { type: mime }) : data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function toCSV(messages: ChatMessage[]): string {
  const esc = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const rows = [["turn", "role", "content", "tool_calls", "sources"].join(",")];
  messages.forEach((m, i) => {
    rows.push(
      [
        String(i + 1),
        m.role,
        esc(m.content),
        esc(JSON.stringify(m.toolCalls ?? [])),
        esc(JSON.stringify(m.sources ?? [])),
      ].join(","),
    );
  });
  return rows.join("\n");
}

function toPDF(messages: ChatMessage[], t: TFunc): Blob {
  const doc = new jsPDF();
  registerPdfFont(doc);
  let y = 15;
  doc.setFontSize(14);
  doc.text(t("export.pdfTitle"), 15, y);
  y += 10;
  doc.setFontSize(10);
  for (const m of messages) {
    const label = m.role === "user" ? t("export.pdfUser") : t("export.pdfAssistant");
    doc.setFont(PDF_FONT_FAMILY, "bold");
    doc.text(label, 15, y);
    y += 6;
    doc.setFont(PDF_FONT_FAMILY, "normal");
    for (const line of doc.splitTextToSize(m.content || "", 180)) {
      if (y > 280) {
        doc.addPage();
        y = 15;
      }
      doc.text(line, 15, y);
      y += 6;
    }
    y += 3;
  }
  return doc.output("blob");
}

/** Export a saved draft letter (Markdown text) as a simple PDF. */
export function draftToPDF(title: string, content: string): Blob {
  const doc = new jsPDF();
  registerPdfFont(doc);
  let y = 15;
  doc.setFontSize(14);
  doc.text(doc.splitTextToSize(title, 180), 15, y);
  y += 12;
  doc.setFontSize(11);
  doc.setFont(PDF_FONT_FAMILY, "normal");
  // Strip the most common markdown markers for the print version.
  const plain = content.replace(/[*_#`>]/g, "");
  for (const line of doc.splitTextToSize(plain, 180)) {
    if (y > 280) {
      doc.addPage();
      y = 15;
    }
    doc.text(line, 15, y);
    y += 6;
  }
  return doc.output("blob");
}

export function ExportMenu({ messages }: { messages: ChatMessage[] }) {
  const [fmt, setFmt] = useState<Format>("JSON");
  const t = useT();
  if (messages.length === 0) return null;

  const onExport = () => {
    if (fmt === "JSON")
      download(JSON.stringify(messages, null, 2), "mietrecht_chat.json", "application/json");
    else if (fmt === "CSV") download(toCSV(messages), "mietrecht_chat.csv", "text/csv");
    else download(toPDF(messages, t), "mietrecht_chat.pdf", "application/pdf");
  };

  return (
    <div className="space-y-2 text-sm">
      <p className="font-semibold">{t("export.title")}</p>
      <div className="flex gap-1">
        {(["JSON", "CSV", "PDF"] as Format[]).map((f) => (
          <button
            key={f}
            onClick={() => setFmt(f)}
            className={`flex-1 rounded-lg border px-2 py-1 text-xs ${
              fmt === f ? "border-primary bg-surface-container text-primary" : "border-outline-variant"
            }`}
          >
            {f}
          </button>
        ))}
      </div>
      <button
        onClick={onExport}
        className="w-full rounded-lg border border-outline-variant px-3 py-1.5 text-sm hover:bg-surface-container"
      >
        {t("export.action", { fmt })}
      </button>
    </div>
  );
}
