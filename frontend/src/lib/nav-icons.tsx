import type { LucideIcon } from "lucide-react";
import {
  Activity,
  FileText,
  FolderOpen,
  LayoutDashboard,
  ScrollText,
  Settings,
  Share2,
  ShieldCheck,
  Upload,
  User,
  UserCog,
  Users,
} from "lucide-react";

/** Map workspace nav hrefs to Lucide icons for consistent sidebar chrome. */
export function getNavIcon(href: string): LucideIcon {
  if (href === "/dashboard" || href === "/admin") return LayoutDashboard;
  if (href === "/documents") return FolderOpen;
  if (href === "/shared") return Share2;
  if (href === "/activity") return Activity;
  if (href === "/documents/upload") return Upload;
  if (href === "/profile") return User;
  if (href === "/request-owner") return UserCog;
  if (href === "/admin/users") return Users;
  if (href === "/admin/promotions") return UserCog;
  if (href === "/admin/audit/views") return FileText;
  if (href === "/admin/audit/integrity") return ShieldCheck;
  if (href === "/admin/audit") return ScrollText;
  return Settings;
}
