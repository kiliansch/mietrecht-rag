// Shared styling + labels for the three German legal verdicts.
import type { Finding } from "../api/types";

type Verdict = Finding["verdict"];

export const VERDICT_META: Record<
  Verdict,
  { label: string; chip: string; tile: string; icon: string }
> = {
  wirksam: {
    label: "Wirksam",
    chip: "bg-success-container text-on-success-container",
    tile: "bg-success-container/40 border-success/30",
    icon: "✅",
  },
  bedenklich: {
    label: "Bedenklich",
    chip: "bg-warning-container text-on-warning-container",
    tile: "bg-warning-container/40 border-warning/30",
    icon: "⚠️",
  },
  unwirksam: {
    label: "Unwirksam",
    chip: "bg-error-container text-on-error-container",
    tile: "bg-error-container/60 border-error/30",
    icon: "❌",
  },
};
