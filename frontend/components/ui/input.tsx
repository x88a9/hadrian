import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-9 w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-1 text-sm text-zinc-100 shadow-sm transition-colors",
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

export { Input };
