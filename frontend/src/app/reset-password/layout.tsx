import type { Metadata } from "next";
import type { ReactNode } from "react";

/**
 * Reset links carry a one-time token in the query string. Avoid indexing and
 * strip referrers so the token is less likely to leak to third parties.
 */
export const metadata: Metadata = {
  title: "Reset password",
  description: "Choose a new TrustVault password using your email reset link.",
  referrer: "no-referrer",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: {
      index: false,
      follow: false,
      noimageindex: true,
    },
  },
};

export default function ResetPasswordLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return children;
}
