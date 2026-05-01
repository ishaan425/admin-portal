export function getRuntimeConfig() {
  return {
    API_URL: window.GROWQR_API_URL || "http://127.0.0.1:8000",
    ORGANIZATION_SLUG: window.GROWQR_ORGANIZATION_SLUG || "amity",
    LOCAL_CLERK_USER_ID: window.GROWQR_LOCAL_CLERK_USER_ID || "local_amity_admin",
    BEARER_TOKEN: window.GROWQR_BEARER_TOKEN || "",
    CLERK_PUBLISHABLE_KEY: window.GROWQR_CLERK_PUBLISHABLE_KEY || "",
    CLERK_FRONTEND_API_URL:
      window.GROWQR_CLERK_FRONTEND_API_URL || "https://amusing-snipe-48.clerk.accounts.dev",
    ALLOW_LOCAL_DEV_LOGIN: window.GROWQR_ALLOW_LOCAL_DEV_LOGIN ?? true,
  };
}
