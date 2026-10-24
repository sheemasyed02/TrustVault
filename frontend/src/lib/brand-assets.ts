/**
 * Public brand image URLs with a cache-bust query.
 * Bump BRAND_ASSET_VERSION whenever you replace files in `frontend/public/`.
 * `unoptimized` next/image + this query avoids stale `/_next/image` responses.
 */
export const BRAND_ASSET_VERSION = "20261024c";

export const LOGO_SRC = `/logo.png?v=${BRAND_ASSET_VERSION}`;
/** Prefer `public/login.png`; keep `loginimg.png` as a fallback name during renames. */
export const LOGIN_HERO_SRC = `/login.png?v=${BRAND_ASSET_VERSION}`;
