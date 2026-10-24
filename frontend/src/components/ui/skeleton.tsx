import type { HTMLAttributes } from "react";

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

/** Loading placeholder that respects reduced-motion preferences. */
export function Skeleton({ className = "", ...rest }: SkeletonProps) {
  return (
    <div
      className={`tv-skeleton ${className}`.trim()}
      aria-hidden
      {...rest}
    />
  );
}

export function SkeletonLines({
  count = 3,
  className = "",
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`.trim()} aria-hidden>
      {Array.from({ length: count }).map((_, index) => (
        <Skeleton
          key={index}
          className={`h-3 ${index === count - 1 ? "w-2/3" : "w-full"}`}
        />
      ))}
    </div>
  );
}
