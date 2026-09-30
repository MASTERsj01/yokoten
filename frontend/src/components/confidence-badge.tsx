import { ShieldCheckIcon, ShieldAlertIcon, ShieldQuestionIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ConfidenceBadge({ label, value }: { label: string; value: number | null }) {
  const Icon = label === "high" ? ShieldCheckIcon : label === "low" ? ShieldAlertIcon : ShieldQuestionIcon;
  return (
    <Badge
      variant="outline"
      title="Confidence = retrieval relevance x share of answer sentences entailed by the sources (NLI)"
      className={cn(
        "gap-1",
        label === "high" && "border-emerald-500/40 text-emerald-700 dark:text-emerald-400",
        label === "medium" && "border-amber-500/40 text-amber-700 dark:text-amber-400",
        label === "low" && "border-red-500/40 text-red-700 dark:text-red-400",
      )}
    >
      <Icon className="size-3.5" />
      {label === "n/a" ? "not answered" : `${label} confidence`}
      {value != null && label !== "n/a" && <span className="text-muted-foreground">{Math.round(value * 100)}%</span>}
    </Badge>
  );
}
