import { createAdminPortalApp } from "./js/adminPortalApp.js?v=page-modules-20260501";
import { getDomRefs } from "./js/domRefs.js?v=page-modules-20260501";
import { getRuntimeConfig } from "./js/runtimeConfig.js?v=page-modules-20260501";

createAdminPortalApp({
  config: getRuntimeConfig(),
  elements: getDomRefs(),
}).init();
