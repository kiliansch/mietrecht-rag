import { useState } from "react";
import type { Source } from "../api/types";
import { useT } from "../i18n";
import { SourceViewer } from "./SourceViewer";

export function SourceList({ sources }: { sources: Source[] }) {
  // De-dupe by URL (else header), so repeated chunks of the same case/§ collapse to
  // one citation, then group by collection.
  const [active, setActive] = useState<Source | null>(null);
  const t = useT();
  const seen = new Set<string>();
  const byCollection: Record<string, Source[]> = {};
  for (const s of sources) {
    const key = s.url || s.header;
    if (seen.has(key)) continue;
    seen.add(key);
    (byCollection[s.source] ??= []).push(s);
  }

  return (
    <div className="space-y-3 text-sm">
      {Object.entries(byCollection).map(([collection, items]) => (
        <div key={collection}>
          <p className="font-semibold mb-1">{t(`source.${collection}`)}</p>
          <ul className="space-y-1">
            {items.map((s, i) => (
              <li key={i} className="text-on-surface-variant">
                {/* Clicking opens the full source in-app (verify without leaving). */}
                <button
                  onClick={() => setActive(s)}
                  className="text-left text-primary hover:underline"
                  title={t("source.viewFull")}
                >
                  {s.header}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {active && <SourceViewer source={active} onClose={() => setActive(null)} />}
    </div>
  );
}
