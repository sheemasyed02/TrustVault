import Image from "next/image";
import type { ReactNode } from "react";

import { BrandLogo } from "@/components/brand-logo";
import { LOGIN_HERO_SRC } from "@/lib/brand-assets";

interface AuthSplitLayoutProps {
  /** Short welcome line shown under the hero image on large screens. */
  welcome?: string;
  /** Supporting sentence under the welcome line. */
  support?: string;
  children: ReactNode;
  /** Optional mark for the marketing panel landmark. */
  marketingLabel?: string;
}

/**
 * Desktop split-screen auth chrome: login hero image + form column.
 * Mobile stacks the image summary above the form.
 */
export function AuthSplitLayout({
  welcome = "Your data. Your control.",
  support = "Accessed only by the right people.",
  children,
  marketingLabel = "TrustVault",
}: AuthSplitLayoutProps) {
  return (
    <div className="flex flex-1 flex-col bg-background lg:flex-row">
      <aside
        aria-label={marketingLabel}
        className="relative flex flex-col overflow-hidden bg-[color-mix(in_srgb,var(--accent-soft)_70%,var(--background))] px-6 py-8 sm:px-10 sm:py-10 lg:w-[48%] lg:justify-between lg:px-12 lg:py-14 xl:px-16"
      >
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_18%_12%,color-mix(in_srgb,var(--accent)_18%,transparent),transparent_52%),radial-gradient(ellipse_at_88%_78%,color-mix(in_srgb,var(--gold)_14%,transparent),transparent_46%)]"
          aria-hidden
        />

        <div className="relative flex items-center gap-3">
          <BrandLogo size="md" decorative priority />
          <div className="min-w-0">
            <p className="font-accent text-xl font-semibold tracking-tight text-foreground">
              TrustVault
            </p>
            <p className="mt-0.5 text-xs font-medium text-muted sm:text-sm">
              Secure Documents. Trusted Access.
            </p>
          </div>
        </div>

        <div className="relative mx-auto mt-8 flex w-full max-w-md flex-1 flex-col items-center justify-center lg:mt-0 lg:max-w-lg">
          <div className="relative w-full max-w-[22rem] sm:max-w-[26rem] lg:max-w-[28rem]">
            <Image
              src={LOGIN_HERO_SRC}
              alt=""
              width={1120}
              height={840}
              priority
              unoptimized
              className="h-auto w-full object-contain drop-shadow-[0_18px_40px_rgba(95,90,139,0.18)]"
              aria-hidden
            />
          </div>
          <p className="mt-6 max-w-sm text-center font-accent text-xl leading-snug text-foreground sm:text-2xl">
            {welcome}
          </p>
          <p className="mt-2 max-w-sm text-center text-sm leading-6 text-muted sm:text-base">
            {support}
          </p>
        </div>
      </aside>

      <div className="flex flex-1 items-center justify-center bg-background px-4 py-8 sm:px-8 sm:py-12 lg:px-10 lg:py-14">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
