// Minimal service worker: no caching, just a fetch handler so the browser
// treats the site as installable ("Add to Home Screen" on Android/Chrome).
self.addEventListener("fetch", () => {});
