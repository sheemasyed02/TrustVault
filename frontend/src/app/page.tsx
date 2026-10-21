import { LoginEntry } from "@/components/login-entry";

export default function HomePage() {
  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-10 px-6 py-12 md:grid-cols-[1.15fr_0.85fr] md:px-10 md:py-16">
      <section className="max-w-xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-strong">
          Confidential documents
        </p>
        <h1 className="mt-4 font-display text-4xl leading-tight tracking-tight text-foreground md:text-5xl">
          TrustVault
        </h1>
        <p className="mt-4 max-w-md text-base leading-7 text-muted md:text-lg">
          Sign in to access documents shared with named permissions. The server
          decides every read, download, and share — not the browser.
        </p>
        <ul className="mt-8 space-y-3 text-sm leading-6 text-muted">
          <li>Short-lived access tokens are kept in memory for this tab only.</li>
          <li>Refreshing the page clears the session; sign in again to continue.</li>
          <li>Role-based menus are guidance only; the API enforces access.</li>
        </ul>
      </section>

      <div className="flex justify-start md:justify-end">
        <LoginEntry />
      </div>
    </div>
  );
}
