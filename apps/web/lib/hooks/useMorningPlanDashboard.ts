import { useQuery } from "@tanstack/react-query";
import { getMorningPlanDashboard } from "@/lib/api/morningPlan";

/**
 * Polls the dashboard on a 60s interval while the tab is visible — the
 * plan itself only changes at 05:45/06:10 or on a manual rerun, but a
 * short poll keeps the countdown-to-open and kill-switch/mode fields
 * current without the user needing to reload (Revision Prompt 15's
 * "calm, information-dense daily operating dashboard" — staying current
 * is part of "calm," a stale screen someone has to manually refresh is not).
 */
export function useMorningPlanDashboard() {
  return useQuery({
    queryKey: ["morning-plan", "dashboard"],
    queryFn: () => getMorningPlanDashboard(),
    refetchInterval: 60_000,
  });
}
