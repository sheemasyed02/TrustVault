import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Forgot password",
  description:
    "Request a TrustVault password reset link. Eligible accounts receive an email when configured.",
  robots: {
    index: false,
    follow: false,
  },
};

export default function ForgotPasswordLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return children;
}
