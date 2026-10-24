"use client";

import { useId, useState, type ReactNode } from "react";

interface TooltipProps {
  content: string;
  children: ReactNode;
  side?: "top" | "bottom";
}

/** Lightweight accessible tooltip for icon-only controls. */
export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined}>{children}</span>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className={`pointer-events-none absolute left-1/2 z-40 w-max max-w-[14rem] -translate-x-1/2 rounded-md bg-sidebar px-2.5 py-1.5 text-xs font-medium text-sidebar-text shadow-[var(--shadow-sm)] ${
            side === "top" ? "bottom-full mb-2" : "top-full mt-2"
          }`}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
