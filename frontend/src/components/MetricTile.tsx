interface Props {
  value: number | string;
  label: string;
  className?: string;
}

// Used for the contract verdict counts (✅/⚠️/❌) and other small stat tiles.
export function MetricTile({ value, label, className = "" }: Props) {
  return (
    <div className={`rounded-xl border p-4 text-center shadow-card ${className}`}>
      <div className="text-3xl font-bold">{value}</div>
      <div className="mt-1 text-sm text-on-surface-variant">{label}</div>
    </div>
  );
}
