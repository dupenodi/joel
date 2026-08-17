import { Progress } from "@/components/ui/progress";

export function StepIndicator({
  step,
  total,
  label,
}: {
  step: number;
  total: number;
  label?: string;
}) {
  return (
    <div>
      {label && <p className="text-sm text-muted">{label}</p>}
      <Progress
        value={total > 0 ? (step / total) * 100 : 0}
        segments={total}
        className="mt-3"
      />
    </div>
  );
}
