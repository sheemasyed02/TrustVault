export function SiteHeader() {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-border/70 px-6 py-5 md:px-10">
      <div className="flex items-baseline gap-3">
        <p className="font-display text-2xl tracking-tight text-foreground md:text-3xl">
          TrustVault
        </p>
        <p className="hidden text-sm text-muted sm:block">
          Secure document sharing
        </p>
      </div>
      <p className="rounded-md bg-accent-soft px-3 py-1 text-xs font-medium text-accent-strong">
        Scaffold
      </p>
    </header>
  );
}
