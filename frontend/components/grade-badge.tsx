import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { gradeColor } from "@/lib/format";
import type { Grade } from "@/lib/types";

interface GradeBadgeProps {
  grade: Grade | null | undefined;
  className?: string;
}

// Kleines Badge fuer einen Grade. Zeigt "—" bei null.
export function GradeBadge({ grade, className }: GradeBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "min-w-8 justify-center font-mono tabular-nums",
        gradeColor(grade),
        className,
      )}
    >
      {grade ?? "—"}
    </Badge>
  );
}
