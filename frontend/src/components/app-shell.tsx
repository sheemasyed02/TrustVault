"use client";

import {
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAuth } from "@/components/auth-provider";
import { BrandLogo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { getNavIcon } from "@/lib/nav-icons";
import {
  getNavSectionsForRole,
  getShellPageMeta,
  isNavItemActive,
  type NavItem,
} from "@/lib/nav";

const COLLAPSE_KEY = "tv-sidebar-collapsed";

function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === "1");
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return { collapsed: ready ? collapsed : false, toggleCollapsed };
}

function NavLinkList({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const pathname = usePathname();

  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = isNavItemActive(pathname, item.href);
        const Icon = getNavIcon(item.href);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              title={collapsed ? item.label : undefined}
              aria-current={active ? "page" : undefined}
              className={`group flex items-center gap-2.5 rounded-[0.625rem] px-3 py-2.5 text-sm font-medium transition-colors duration-[180ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold ${
                collapsed ? "justify-center px-2" : ""
              } ${
                active
                  ? "bg-[var(--sidebar-active)] text-sidebar-text shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--gold)_28%,transparent)]"
                  : "text-sidebar-text/85 hover:bg-[var(--sidebar-hover)] hover:text-sidebar-text"
              }`}
            >
              <Icon
                className={`h-4 w-4 shrink-0 ${
                  active
                    ? "text-gold"
                    : "text-sidebar-text/70 group-hover:text-gold"
                }`}
                strokeWidth={1.75}
                aria-hidden
              />
              {!collapsed ? <span className="truncate">{item.label}</span> : null}
              {collapsed ? <span className="sr-only">{item.label}</span> : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function SidebarBody({
  collapsed,
  onNavigate,
  showCollapseControl,
  onToggleCollapse,
}: {
  collapsed: boolean;
  onNavigate: () => void;
  showCollapseControl?: boolean;
  onToggleCollapse?: () => void;
}) {
  const { user, logout } = useAuth();
  if (!user) return null;

  const sections = getNavSectionsForRole(user.role);

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div
        className={`flex items-center gap-2.5 border-b border-[color-mix(in_srgb,var(--sidebar-text)_10%,transparent)] px-4 py-4 ${
          collapsed ? "justify-center px-2" : "px-5"
        }`}
      >
        <BrandLogo
          size="sm"
          decorative
          className="rounded-md bg-white/95 p-0.5"
        />
        {!collapsed ? (
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold tracking-tight text-sidebar-text">
              TrustVault
            </p>
            <p className="mt-0.5 truncate font-accent text-xs text-gold">
              Secure by design
            </p>
          </div>
        ) : null}
        {showCollapseControl && onToggleCollapse ? (
          <Button
            size="sm"
            variant="secondary"
            className="hidden border-transparent bg-white/10 text-sidebar-text hover:bg-white/15 lg:inline-flex"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            ) : (
              <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
          </Button>
        ) : null}
      </div>

      <div
        className={`min-h-0 flex-1 overflow-y-auto px-3 py-4 ${
          collapsed ? "px-2" : ""
        }`}
      >
        <p
          className={`mb-3 px-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-sidebar-muted ${
            collapsed ? "sr-only" : ""
          }`}
        >
          {user.role} workspace
        </p>

        <nav id="app-sidebar-nav" aria-label="Workspace" className="space-y-5">
          {sections.map((section) => (
            <div key={section.id}>
              {section.label && !collapsed ? (
                <p className="mb-1.5 px-3 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-sidebar-muted">
                  {section.label}
                </p>
              ) : null}
              {section.label && collapsed ? (
                <div
                  className="mx-auto mb-1.5 h-px w-6 bg-[color-mix(in_srgb,var(--sidebar-text)_14%,transparent)]"
                  aria-hidden
                />
              ) : null}
              <NavLinkList
                items={section.items}
                collapsed={collapsed}
                onNavigate={onNavigate}
              />
            </div>
          ))}
        </nav>
      </div>

      <div
        className={`mt-auto border-t border-[color-mix(in_srgb,var(--sidebar-text)_10%,transparent)] p-3 ${
          collapsed ? "px-2" : ""
        }`}
      >
        <div
          className={`rounded-[0.75rem] bg-[var(--sidebar-hover)] ${
            collapsed ? "p-2" : "px-3 py-3"
          }`}
        >
          {!collapsed ? (
            <>
              <p className="truncate text-sm font-medium text-sidebar-text">
                {user.name}
              </p>
              <p className="mt-0.5 truncate text-xs text-sidebar-muted">
                {user.email}
              </p>
              <div className="mt-3 flex flex-col gap-1.5">
                <Link
                  href="/profile"
                  onClick={onNavigate}
                  className="inline-flex items-center justify-center gap-1.5 rounded-[0.5rem] bg-white/10 px-2.5 py-1.5 text-xs font-semibold text-sidebar-text transition-colors duration-[180ms] hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold"
                >
                  <UserRound className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  Profile
                </Link>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full border-transparent bg-white/10 text-sidebar-text hover:bg-white/15"
                  onClick={() => logout()}
                >
                  <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  Sign out
                </Button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-1.5">
              <Link
                href="/profile"
                onClick={onNavigate}
                title="Profile"
                aria-label="Profile"
                className="inline-flex h-8 w-8 items-center justify-center rounded-[0.5rem] bg-white/10 text-sidebar-text transition-colors duration-[180ms] hover:bg-white/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gold"
              >
                <UserRound className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Link>
              <Button
                variant="secondary"
                size="sm"
                className="h-8 w-8 border-transparent bg-white/10 p-0 text-sidebar-text hover:bg-white/15"
                onClick={() => logout()}
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AppHeader({
  drawerOpen,
  onOpenDrawer,
  collapsed,
  onToggleCollapse,
}: {
  drawerOpen: boolean;
  onOpenDrawer: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  if (!user) return null;

  const meta = getShellPageMeta(pathname, user.role);

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-[color-mix(in_srgb,var(--background)_92%,white)] backdrop-blur-sm">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 sm:px-6 md:px-8">
        {/* Wrapper owns display toggles — Button base uses inline-flex which can fight Tailwind `hidden`. */}
        <div className="lg:hidden">
          <Button
            size="sm"
            variant="secondary"
            onClick={onOpenDrawer}
            aria-expanded={drawerOpen}
            aria-controls="mobile-nav-drawer"
            aria-label="Open navigation"
          >
            <Menu className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        </div>

        <div className="hidden lg:block">
          <Button
            size="sm"
            variant="ghost"
            className="text-muted"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            ) : (
              <ChevronLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden />
            )}
          </Button>
        </div>

        <div className="min-w-0 flex-1">
          {meta.crumbs.length > 1 ? (
            <nav aria-label="Breadcrumb" className="mb-0.5">
              <ol className="flex flex-wrap items-center gap-1 text-xs text-muted">
                {meta.crumbs.map((crumb, index) => {
                  const isLast = index === meta.crumbs.length - 1;
                  return (
                    <li key={`${crumb.label}-${index}`} className="flex items-center gap-1">
                      {index > 0 ? (
                        <span aria-hidden className="text-border">
                          /
                        </span>
                      ) : null}
                      {crumb.href && !isLast ? (
                        <Link
                          href={crumb.href}
                          className="font-medium text-accent-strong hover:underline"
                        >
                          {crumb.label}
                        </Link>
                      ) : (
                        <span className={isLast ? "text-muted" : undefined}>
                          {crumb.label}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </nav>
          ) : null}
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h1 className="truncate text-base font-semibold tracking-tight text-foreground sm:text-lg">
              {meta.title}
            </h1>
            {meta.subtitle ? (
              <p className="truncate text-xs text-muted sm:text-sm">{meta.subtitle}</p>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
          <div className="hidden min-w-0 text-right sm:block">
            <p className="truncate text-sm font-medium text-foreground">
              {user.name}
            </p>
            <p className="truncate text-xs text-muted">{user.role}</p>
          </div>
          <Link
            href="/profile"
            aria-label="Profile"
            className={
              "inline-flex h-9 min-w-9 items-center justify-center gap-1.5 rounded-[0.625rem] border border-border bg-surface px-2.5 text-xs font-semibold text-foreground transition-colors duration-[180ms] hover:bg-accent-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:px-3"
            }
          >
            <UserRound className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            <span className="hidden sm:inline">Profile</span>
          </Link>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => logout()}
            aria-label="Sign out"
            className="min-w-9"
          >
            <LogOut className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
            <span className="hidden sm:inline" aria-hidden>
              Sign out
            </span>
          </Button>
        </div>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const { collapsed, toggleCollapsed } = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerTitleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
  const openDrawer = useCallback(() => setDrawerOpen(true), []);

  useEffect(() => {
    closeDrawer();
  }, [pathname, closeDrawer]);

  useEffect(() => {
    if (!drawerOpen) return;

    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const frame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer();
      }
    }

    window.addEventListener("keydown", onKey);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [drawerOpen, closeDrawer]);

  if (!user) return null;

  return (
    <div className="flex min-h-screen flex-1 bg-background">
      {/* Desktop sidebar */}
      <aside
        className={`sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar text-sidebar-text transition-[width] duration-[200ms] ease-out lg:flex ${
          collapsed ? "w-[4.5rem]" : "w-64"
        }`}
        aria-label="Workspace sidebar"
      >
        <SidebarBody
          collapsed={collapsed}
          onNavigate={() => undefined}
          showCollapseControl
          onToggleCollapse={toggleCollapsed}
        />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="presentation">
          <button
            type="button"
            className="absolute inset-0 bg-[color-mix(in_srgb,var(--sidebar)_55%,transparent)] backdrop-blur-[1px]"
            aria-label="Close navigation"
            onClick={closeDrawer}
          />
          <div
            id="mobile-nav-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby={drawerTitleId}
            className="absolute inset-y-0 left-0 flex w-[min(18.5rem,88vw)] flex-col bg-sidebar text-sidebar-text shadow-[var(--shadow)]"
          >
            <div className="flex items-center justify-between gap-2 border-b border-[color-mix(in_srgb,var(--sidebar-text)_10%,transparent)] px-4 py-3">
              <p
                id={drawerTitleId}
                className="text-sm font-semibold text-sidebar-text"
              >
                Navigation
              </p>
              <Button
                ref={closeButtonRef}
                size="sm"
                variant="secondary"
                className="border-transparent bg-white/10 text-sidebar-text hover:bg-white/15"
                onClick={closeDrawer}
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </div>
            <SidebarBody collapsed={false} onNavigate={closeDrawer} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader
          drawerOpen={drawerOpen}
          onOpenDrawer={openDrawer}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapsed}
        />
        <div className="mx-auto w-full max-w-6xl flex-1 px-4 py-5 sm:px-6 sm:py-6 md:px-8 md:py-8">
          {children}
        </div>
      </div>
    </div>
  );
}
