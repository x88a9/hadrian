import { cn } from "@/lib/utils";
import { STAGE_LABEL, stageColor } from "@/lib/live-format";
import type { LiveStage } from "@/lib/types";

export function LiveStageBadge({
  stage,
  className,
}: {
  stage: LiveStage;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        stageColor(stage),
        className,
      )}
    >
      {STAGE_LABEL[stage]}
    </span>
  );
}
