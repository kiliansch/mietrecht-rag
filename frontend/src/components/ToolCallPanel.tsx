import { useState } from "react";
import type { ToolCall } from "../api/types";
import { useT } from "../i18n";
import { Icon } from "./Icon";

export function ToolCallPanel({ toolCalls }: { toolCalls: ToolCall[] }) {
  return (
    <div className="space-y-2">
      {toolCalls.map((tc) => (
        <ToolCallItem key={tc.id} tc={tc} />
      ))}
    </div>
  );
}

function ToolCallItem({ tc }: { tc: ToolCall }) {
  const [open, setOpen] = useState(false);
  const t = useT();
  const result = tc.result && tc.result.length > 1000 ? tc.result.slice(0, 1000) + " …" : tc.result;
  return (
    <div className="rounded-lg border border-outline-variant bg-surface-container-low">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-on-surface-variant"
      >
        <Icon name="build" className="text-base" />
        <span className="font-medium">
          {t("tool.used")}: <code className="font-mono">{tc.name}</code>
        </span>
        <Icon name={open ? "expand_less" : "expand_more"} className="ml-auto text-base" />
      </button>
      {open && (
        <div className="border-t border-outline-variant px-3 py-2 text-xs">
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-on-surface-variant">
            {JSON.stringify(tc.args, null, 2)}
          </pre>
          {result && (
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap border-t border-outline-variant pt-2 font-mono text-on-surface-variant">
              {result}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
