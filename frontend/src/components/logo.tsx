import { cn } from "@/lib/utils";

/** The Settle mark: two level bars, a case brought to balance. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path
        d="M9 12.5h14M9 19.5h14"
        strokeWidth="3"
        strokeLinecap="round"
        className="stroke-primary-foreground"
      />
    </svg>
  );
}
