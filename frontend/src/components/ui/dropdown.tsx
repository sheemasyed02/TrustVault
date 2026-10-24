"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Button, type ButtonVariant } from "@/components/ui/button";

export interface DropdownItem {
  id: string;
  label: string;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
}

interface DropdownProps {
  label: string;
  items: DropdownItem[];
  variant?: ButtonVariant;
  size?: "sm" | "md";
  align?: "left" | "right";
  icon?: ReactNode;
}

/** Simple menu for overflow / secondary actions. */
export function Dropdown({
  label,
  items,
  variant = "secondary",
  size = "sm",
  align = "right",
  icon,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-flex">
      <Button
        type="button"
        variant={variant}
        size={size}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
      >
        {icon}
        {label}
      </Button>
      {open ? (
        <ul
          id={menuId}
          role="menu"
          className={`absolute z-40 mt-1.5 min-w-[10rem] overflow-hidden rounded-[0.75rem] border border-border bg-surface py-1 shadow-[var(--shadow)] ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item) => (
            <li key={item.id} role="none">
              <button
                type="button"
                role="menuitem"
                disabled={item.disabled}
                className={`flex w-full px-3 py-2 text-left text-sm transition-colors duration-[160ms] disabled:opacity-50 ${
                  item.danger
                    ? "text-danger hover:bg-[color-mix(in_srgb,var(--danger)_8%,white)]"
                    : "text-foreground hover:bg-accent-soft"
                }`}
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
