import { useWorkspace } from "../state/workspace";
import { useT, type TFunc } from "../i18n";

const CURRENCY_KEYS = new Set(["monthly_net_rent", "current_rent", "local_comparable_rent"]);
const num = (v: unknown) => new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }).format(Number(v));

function factLabel(t: TFunc, key: string): string {
  const label = t(`fact.${key}`);
  return label === `fact.${key}` ? key : label; // fall back to the raw key if unmapped
}

function formatFact(t: TFunc, key: string, value: string | number | boolean): string {
  if (typeof value === "boolean") return value ? t("mietfall.yes") : t("mietfall.no");
  if (CURRENCY_KEYS.has(key)) return `${num(value)} €`;
  if (key === "floor_area_sqm") return `${num(value)} m²`;
  if (key === "tenancy_years") return `${num(value)} ${t("mietfall.years")}`;
  return String(value);
}

export function MietfallPanel() {
  const { profile } = useWorkspace();
  const t = useT();

  const facts = profile?.facts ?? {};
  const factKeys = Object.keys(facts);
  const empty = factKeys.length === 0;

  return (
    <div className="space-y-2 text-sm">
      <p className="font-semibold text-on-surface">{t("sidebar.mietfall")}</p>

      {factKeys.length > 0 && (
        <ul className="space-y-1 text-on-surface-variant">
          {factKeys.map((k) => (
            <li key={k}>
              {factLabel(t, k)}: {formatFact(t, k, facts[k])}
              {profile?.facts_source?.[k] === "contract" && (
                <span className="ml-1 rounded bg-surface-container px-1 text-xs">{t("mietfall.fromContract")}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {empty && <p className="text-on-surface-variant">{t("mietfall.empty")}</p>}
    </div>
  );
}
