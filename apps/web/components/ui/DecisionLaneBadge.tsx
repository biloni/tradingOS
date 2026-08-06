export type DecisionLane = "INVESTMENT" | "TACTICAL";

const LANE_COPY: Record<DecisionLane, { label: string; icon: string; classes: string }> = {
  INVESTMENT: {
    label: "Investment",
    icon: "◆",
    classes: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
  },
  TACTICAL: {
    label: "Tactical",
    icon: "▲",
    classes: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300",
  },
};

/**
 * PRODUCT MODES (PROJECT_INSTRUCTIONS.md v2 amendment, PM-1/PM-2): every
 * Investment/Tactical recommendation must be visually tagged, never
 * merged. The lane's shape/icon differs (◆ vs ▲), not only its color, so
 * this remains distinguishable without color (accessibility requirement).
 */
export function DecisionLaneBadge({ lane }: { lane: DecisionLane }) {
  const copy = LANE_COPY[lane];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${copy.classes}`}
    >
      <span aria-hidden="true">{copy.icon}</span>
      {copy.label}
    </span>
  );
}
