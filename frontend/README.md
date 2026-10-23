# TrustVault frontend

Next.js App Router + TypeScript + Tailwind CSS. Deployed on **Vercel**.

The browser talks to the FastAPI backend using `NEXT_PUBLIC_API_BASE_URL` and
`Authorization: Bearer` access tokens kept in memory (not `localStorage`).

Never put `DATABASE_URL`, `JWT_SECRET_KEY`, or R2 secrets in frontend env files.

## Setup

```powershell
cd D:\TrustVault\frontend
copy .env.example .env.local
# NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm install
```

## Run

```powershell
npm run dev
```

Open http://localhost:3000

## Lint, test, and production build

```powershell
npm run lint
npm test -- --run
npm run build
```

## Vercel

1. Root Directory: `frontend`
2. Build: `npm run build` (default)
3. Environment: `NEXT_PUBLIC_API_BASE_URL=https://<your-render-api-host>`
4. Add the Vercel origin to backend `CORS_ORIGINS` on Render

See the repository root [`../README.md`](../README.md) for the full deployment runbook.
