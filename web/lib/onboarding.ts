export const ONBOARDING_STEPS = [
  "workspace",
  "models",
  "composio",
  "sources",
  "slack",
  "people",
  "mcp",
  "voice",
] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

export const STEP_META: Record<OnboardingStep, string> = {
  workspace: "Workspace",
  models: "Models",
  composio: "Connect broker",
  sources: "Sources",
  slack: "Slack",
  people: "People",
  mcp: "MCP",
  voice: "Voice",
};

const LEGACY: Record<string, OnboardingStep> = {
  llm: "models",
  tools: "sources",
};

export function isOnboardingStep(value: string | undefined): value is OnboardingStep {
  return (
    value === "workspace" ||
    value === "models" ||
    value === "composio" ||
    value === "sources" ||
    value === "slack" ||
    value === "people" ||
    value === "mcp" ||
    value === "voice"
  );
}

export function resolveOnboardingStep(value: string | undefined): OnboardingStep | null {
  if (!value) return null;
  if (isOnboardingStep(value)) return value;
  return LEGACY[value] ?? null;
}

export function onboardingPath(step: OnboardingStep): string {
  return `/onboarding/${step}`;
}

export function nextOnboardingStep(step: OnboardingStep): OnboardingStep | "home" {
  const i = ONBOARDING_STEPS.indexOf(step);
  if (i < 0 || i >= ONBOARDING_STEPS.length - 1) return "home";
  return ONBOARDING_STEPS[i + 1]!;
}
