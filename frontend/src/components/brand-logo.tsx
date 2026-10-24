import Image from "next/image";

import { LOGO_SRC } from "@/lib/brand-assets";

const SIZE_PX = {
  sm: 28,
  md: 40,
  lg: 64,
} as const;

export interface BrandLogoProps {
  /** sm: header/sidebar · md: compact hero · lg: auth marketing panels */
  size?: keyof typeof SIZE_PX;
  className?: string;
  /**
   * When the adjacent text already says “TrustVault”, mark the image decorative
   * so screen readers do not announce the brand twice.
   */
  decorative?: boolean;
  /** Prefer true on primary auth/marketing surfaces for LCP. */
  priority?: boolean;
}

export function BrandLogo({
  size = "sm",
  className = "",
  decorative = false,
  priority = false,
}: BrandLogoProps) {
  const px = SIZE_PX[size];

  return (
    <Image
      src={LOGO_SRC}
      alt={decorative ? "" : "TrustVault"}
      width={px}
      height={px}
      priority={priority}
      unoptimized
      className={`shrink-0 object-contain ${className}`.trim()}
      style={{ width: px, height: px }}
      aria-hidden={decorative ? true : undefined}
    />
  );
}
