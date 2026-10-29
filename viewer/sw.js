/* JARVIS — service worker.
 *
 * Règle unique : ne JAMAIS mettre en cache ce qui est personnel.
 * La page, le graphe et les API viennent toujours du réseau : c'est ce qui
 * garantit qu'un changement de compte ne sert pas les notes d'un autre.
 * Seules les ressources de présentation (styles, script, images, icônes) sont
 * conservées, pour que l'interface s'affiche instantanément.
 */
const CACHE = "jarvis-shell-v1";

const SHELL = [
  "/styles.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/favicon.ico",
  "/assets/jarvis-core-ring.avif",
  "/assets/jarvis-core-veil.avif",
  "/assets/jarvis-core-disc.avif",
  "/assets/jarvis-core-light.avif",
  "/assets/jarvis-core-hud-violet.avif",
  "/assets/jarvis-core-hud-ambre.avif",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // Une ressource manquante ne doit pas empêcher l'installation.
      Promise.allSettled(SHELL.map((url) => cache.add(url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

const NEVER_CACHE = ["/", "/index.html", "/graph-data.js", "/api/", "/auth/"];

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE.some((prefix) => url.pathname === prefix || url.pathname.startsWith(prefix))) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok && response.type === "basic") {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
