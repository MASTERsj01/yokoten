import { Loader2Icon } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function StatusBadge({ status }: { status: string }) {
  if (status === "ready")
    return <Badge className="bg-emerald-600/15 text-emerald-700 dark:text-emerald-400">ready</Badge>;
  if (status === "error") return <Badge variant="destructive">error</Badge>;
  return (
    <Badge variant="secondary" className="gap-1">
      <Loader2Icon className="size-3 animate-spin" /> {status}
    </Badge>
  );
}
