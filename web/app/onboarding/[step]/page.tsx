import { OnboardingFlow } from "@/components/onboarding-flow";

export default async function OnboardingStepPage({
  params,
}: {
  params: Promise<{ step: string }>;
}) {
  const { step } = await params;
  return <OnboardingFlow requested={step} />;
}
