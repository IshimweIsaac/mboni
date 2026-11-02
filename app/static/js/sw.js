/* Mboni service worker: offline shell, cached static files and downloaded films. */
const SHELL = "mboni-shell-v3";
const DOWNLOADS = "mboni-downloads";
const SHELL_FILES = ["/offline", "/static/css/app.css", "/static/js/app.js", "/static/js/player.js",
  "/static/icons/icon.svg", "/static/icons/icon-192.png", "/static/manifest.json",
  "/static/subs/en.vtt", "/static/subs/rw.vtt", "/static/subs/fr.vtt"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== DOWNLOADS).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Videos are requested with Range headers, so answer from the downloaded copy with a 206 slice.
async function fromDownloads(request) {
  const cache = await caches.open(DOWNLOADS);
  const hit = await cache.match(request.url);
  if (!hit) return null;
  const range = request.headers.get("range");
  if (!range) return hit;
  const blob = await hit.blob();
  const [, startStr, endStr] = /bytes=(\d*)-(\d*)/.exec(range) || [];
  const start = Number(startStr || 0);
  const end = endStr ? Number(endStr) : blob.size - 1;
  return new Response(blob.slice(start, end + 1), {
    status: 206,
    headers: {
      "Content-Type": hit.headers.get("Content-Type") || "video/mp4",
      "Content-Range": `bytes ${start}-${end}/${blob.size}`,
      "Content-Length": String(end - start + 1),
      "Accept-Ranges": "bytes",
    },
  });
}

self.addEventListener("fetch", (e) => {
  const { request } = e;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname.startsWith("/static/media/")) {
    e.respondWith(fromDownloads(request).then((r) => r || fetch(request)));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    // Network first so updates show at once; the cached copy keeps the app working offline.
    e.respondWith(fetch(request).then((res) => {
      const copy = res.clone();
      if (res.ok) caches.open(SHELL).then((c) => c.put(request, copy));
      return res;
    }).catch(() => caches.match(request)));
    return;
  }
  if (request.mode === "navigate") {
    // Pages are always fresh when online; offline falls back to the last copy or the offline page.
    e.respondWith(fetch(request).then((res) => {
      const copy = res.clone();
      if (res.ok) caches.open(SHELL).then((c) => c.put(request, copy));
      return res;
    }).catch(async () => (await caches.match(request)) || caches.match("/offline")));
  }
});
