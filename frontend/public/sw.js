/* EdgeBet – service worker minimal.
 * - Coquille applicative (index, manifest, icônes, assets hachés) : cache-first.
 * - Navigations : network-first avec repli sur index.html (hors ligne).
 * - /api : network-first, repli sur la dernière réponse connue (GET uniquement).
 * __BUILD_ID__ est remplacé au build Docker pour invalider les anciens caches.
 */
const VERSION = "edgebet-__BUILD_ID__";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icons/icon.svg", "/icons/icon-maskable.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // API distante ou CDN : on ne touche pas

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(req));
  } else if (req.mode === "navigate") {
    event.respondWith(networkFirst(req, "/index.html"));
  } else {
    event.respondWith(cacheFirst(req));
  }
});

async function networkFirst(req, fallbackKey) {
  const cache = await caches.open(VERSION);
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const cached = (await cache.match(req)) || (fallbackKey ? await cache.match(fallbackKey) : undefined);
    if (cached) return cached;
    return new Response(JSON.stringify({ detail: "Hors ligne" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(VERSION);
  const cached = await cache.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res && res.ok) cache.put(req, res.clone());
  return res;
}
