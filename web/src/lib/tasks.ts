/** Task plans sit on top of a rules-engine answer. They never run if that answer was a refusal. */

export type TaskStep = { label: string; tab?: string; ask?: string; why?: boolean };
export type TaskPlan = { title: string; steps: TaskStep[]; state: "pending" | "running" | "done" | "cancelled" };

const TASKS: { test: RegExp; title: string; steps: TaskStep[] }[] = [
  {
    test: /morning check|what should i look at|check the alerts/,
    title: "Morning check",
    steps: [
      { label: "Open Alerts. Each alert is already a governed check.", tab: "alerts" },
      { label: "Ask how reliable the agents are.", ask: "How reliable are our agents?" },
    ],
  },
  {
    test: /board pack|tell the board|renewal pack|cost case|prepare the renewal/,
    title: "Renewal pack",
    steps: [
      { label: "Ask licence utilisation.", ask: "What is licence utilisation this month?" },
      { label: "Ask the licence funnel and unused seats.", ask: "Show the licence funnel and unused seats" },
      { label: "Ask the renewal outcome.", ask: "What renewal outcome do you recommend?" },
      { label: "Open the board pack. The note is those answers. Nothing is sent.", tab: "pack" },
    ],
  },
  {
    test: /right-?\s*size|take back|reclaim/,
    title: "Right-size",
    steps: [
      { label: "Open What-if. The seat file is not changed.", tab: "whatif" },
      { label: "Open Seats and bill.", tab: "seats" },
    ],
  },
  {
    test: /compare (the )?(scenarios|datasets)|baseline and healthy|two datasets/,
    title: "Scenario check",
    steps: [
      { label: "Open Compare. The live dataset stays as it is, so this thread is kept.", tab: "compare" },
    ],
  },
  {
    test: /explain (this |the )?number|open the lineage/,
    title: "Explain this number",
    steps: [
      { label: "Open the lineage for the metrics in the answer above.", why: true },
    ],
  },
];

export function planFor(question: string, answerType: string | undefined, answerText?: string): TaskPlan | null {
  if (!answerType || answerType === "clarify" || answerType === "error") return null;
  const unmapped = answerType === "refuse" && (answerText || "").includes("I couldn't map that");
  if (answerType === "refuse" && !unmapped) return null;
  const hit = TASKS.find((t) => t.test.test(question.toLowerCase()));
  if (!hit) return null;
  return { title: hit.title, steps: hit.steps.map((s) => ({ ...s })), state: "pending" };
}
