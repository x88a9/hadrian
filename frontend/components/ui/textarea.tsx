import * as React from "react";

import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex min-h-20 w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-100 shadow-sm transition-colors",
        "placeholder:text-zinc-600",
        "outline-none hover:border-zinc-700 focus-visible:border-zinc-600 focus-visible:ring-2 focus-visible:ring-zinc-700/60",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-red-500/60 aria-invalid:focus-visible:ring-red-500/20",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
