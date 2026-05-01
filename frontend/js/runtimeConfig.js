export function getRuntimeConfig() {
  return {
    API_URL: window.GROWQR_API_URL || "http://127.0.0.1:8000",
    ORGANIZATION_SLUG: window.GROWQR_ORGANIZATION_SLUG || "amity",
    CLERK_PUBLISHABLE_KEY: window.GROWQR_CLERK_PUBLISHABLE_KEY || "",
    CLERK_FRONTEND_API_URL:
      window.GROWQR_CLERK_FRONTEND_API_URL || "https://amusing-snipe-48.clerk.accounts.dev",
  };
}
