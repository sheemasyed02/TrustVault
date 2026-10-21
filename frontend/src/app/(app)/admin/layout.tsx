import type { ReactNode } from "react";

import { RequireAdmin } from "@/components/require-admin";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <RequireAdmin>{children}</RequireAdmin>;
}
