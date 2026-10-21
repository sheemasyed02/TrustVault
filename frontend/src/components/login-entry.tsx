export function LoginEntry() {
  return (
    <section
      aria-labelledby="sign-in-heading"
      className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-[var(--shadow)] backdrop-blur md:p-8"
    >
      <h2
        id="sign-in-heading"
        className="font-display text-2xl tracking-tight text-foreground"
      >
        Sign in
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted">
        Authentication is not implemented in this scaffold. The form below is
        UI only and does not submit credentials.
      </p>

      <form className="mt-6 space-y-4">
        <div className="space-y-2">
          <label htmlFor="email" className="block text-sm font-medium">
            Work email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            disabled
            placeholder="you@company.com"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm text-foreground outline-none ring-accent/40 placeholder:text-muted/80 disabled:cursor-not-allowed disabled:opacity-70"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            disabled
            placeholder="••••••••"
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm text-foreground outline-none ring-accent/40 placeholder:text-muted/80 disabled:cursor-not-allowed disabled:opacity-70"
          />
        </div>

        <button
          type="button"
          disabled
          className="w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white opacity-70"
        >
          Sign in unavailable
        </button>
      </form>
    </section>
  );
}
