# Frontend Structure

This is a static admin frontend served from `frontend/`.

- `index.html` owns the page markup.
- `styles.css` owns the current visual system.
- `config.js` is the local runtime configuration you can edit.
- `app.js` is the small browser entry point.
- `js/runtimeConfig.js` reads config values from `window`.
- `js/domRefs.js` keeps DOM selectors in one place.
- `js/batchModel.js` normalizes upload batch data into dashboard/student stats.
- `js/adminPortalApp.js` owns app shell behavior: auth, onboarding, routing, upload, and polling.
- `js/pages/dashboardPage.js` owns dashboard rendering.
- `js/pages/studentsPage.js` owns student/user table rendering, filters, selection, and CSV export.
- `js/utils.js` owns small shared formatting helpers.

Run locally:

```sh
npm --prefix frontend run dev
```
