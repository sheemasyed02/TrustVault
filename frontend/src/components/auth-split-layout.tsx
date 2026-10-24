import {
  FileKey2,
  LockKeyhole,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { BrandLogo } from "@/components/brand-logo";

interface AuthSplitLayoutProps {
  /** Short Merienda welcome / decorative accent. */
  welcome: string;
  /** One concise Manrope supporting sentence. */
  support: string;
  children: ReactNode;
  /** Optional mark for the marketing panel landmark. */
  marketingLabel?: string;
}

const accents: { Icon: LucideIcon; label: string }[] = [
  { Icon: ShieldCheck, label: "Server-side access control" },
  { Icon: LockKeyhole, label: "Named document permissions" },
  { Icon: FileKey2, label: "Auditable activity trail" },
];

/**
 * Desktop split-screen auth chrome: ivory/lavender brand panel + white form column.
 * Mobile stacks brand summary above the form.
 */
export function AuthSplitLayout({
  welcome,
  support,
  children,
  marketingLabel = "TrustVault",
}: AuthSplitLayoutProps) {
  return (
    <div className="flex flex-1 flex-col lg:flex-row">
      <aside
        aria-label={marketingLabel}
        className="relative flex flex-col justify-between overflow-hidden bg-accent-soft px-6 py-8 sm:px-10 sm:py-10 lg:w-[46%] lg:px-12 lg:py-14 xl:px-16"
      >
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_20%_0%,color-mix(in_srgb,var(--gold)_16%,transparent),transparent_48%),radial-gradient(ellipse_at_90%_80%,color-mix(in_srgb,var(--accent)_12%,transparent),transparent_42%)]"
          aria-hidden
        />

        <div className="relative">
          <div className="flex items-center gap-3">
            <BrandLogo size="md" decorative priority />
            <p className="text-xl font-semibold tracking-tight text-foreground">
              TrustVault
            </p>
          </div>
          <p className="mt-8 max-w-sm font-accent text-2xl leading-snug text-foreground sm:text-3xl">
            {welcome}
          </p>
          <p className="mt-3 max-w-sm text-sm leading-6 text-muted sm:text-base">
            {support}
          </p>
        </div>

        <ul className="relative mt-10 hidden flex-col gap-3 sm:flex lg:mt-0 lg:gap-4">
          {accents.map(({ Icon, label }) => (
            <li
              key={label}
              className="flex items-center gap-3 rounded-[0.875rem] border border-border/80 bg-surface/70 px-3.5 py-3 shadow-[var(--shadow-sm)] backdrop-blur-[2px]"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[0.625rem] bg-sidebar text-gold">
                <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </span>
              <span className="text-sm font-medium text-foreground">{label}</span>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex flex-1 items-center justify-center bg-background px-4 py-8 sm:px-8 sm:py-12 lg:px-10 lg:py-14">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
