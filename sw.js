/*
 * Service worker for Mandi Rates · Karnataka.
 *
 * Three caching strategies, one per kind of request:
 *
 *   app shell (HTML)  network-first, cache fallback -- so a deployed change
 *                     shows up on the next online launch, but the app still
 *                     opens with no signal at all.
 *   static assets     cache-first -- icons and the manifest never change
 *                     without a SHELL_CACHE version bump.
 *   data JSON         network-first, cache fallback -- prices must be the
 *                     live ones when there's a connection, and the last
 *                     known ones when there isn't.
 *
 * Bump CACHE_VERSION whenever index.html or the icons change; the activate
 * handler deletes every cache that doesn't match the current version.
 */

const CACHE_VERSION = 'v1';
const SHELL_CACHE = `mandi-shell-${CACHE_VERSION}`;
const DATA_CACHE = `mandi-data-${CACHE_VERSION}`;
const FONT_CACHE = `mandi-fonts-${CACHE_VERSION}`;
const CURRENT_CACHES = [SHELL_CACHE, DATA_CACHE, FONT_CACHE];

// Relative so the worker keeps working under a GitHub Pages project path
// (/karnataka-mandi-rates/) as well as at a domain root.
const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-192.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png',
  './icons/favicon-32.png',
];

// Seeding the data caches at install time is what makes a first launch in
// airplane mode show prices instead of an empty table.
const DATA_ASSETS = ['./data/live.json', './data/history.json'];

const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];

/* The app appends `?_=<timestamp>` to defeat HTTP caching on data requests.
 * Left alone that would mean every single fetch is a cache miss *and* a new
 * cache entry, so the cache would grow forever while never once serving a
 * hit. Both the read and the write side key off the bare path instead. */
function dataCacheKey(url) {
  const u = new URL(url);
  u.search = '';
  return u.toString();
}

function isDataRequest(url) {
  return url.pathname.endsWith('/data/live.json') || url.pathname.endsWith('/data/history.json');
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const shell = await caches.open(SHELL_CACHE);
      await shell.addAll(SHELL_ASSETS);

      // Best-effort: a failed data prefetch must not fail the install and
      // leave the app with no worker at all.
      const data = await caches.open(DATA_CACHE);
      await Promise.all(
        DATA_ASSETS.map(async (path) => {
          try {
            const res = await fetch(path, { cache: 'no-store' });
            if (res.ok) await data.put(dataCacheKey(new URL(path, self.location).href), res);
          } catch (_) {
            /* offline at install time -- the first online fetch will fill it */
          }
        })
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((n) => !CURRENT_CACHES.includes(n)).map((n) => caches.delete(n)));
      await self.clients.claim();
    })()
  );
});

async function networkFirst(request, cacheName, key) {
  const cache = await caches.open(cacheName);
  const cacheKey = key || request;
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(cacheKey, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok || res.type === 'opaque') cache.put(request, res.clone());
  return res;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Google Fonts: cache-first, since a webfont at a versioned URL is
  // immutable. Keeps the masthead and Kannada text correct offline.
  if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request, FONT_CACHE).catch(() => fetch(request)));
    return;
  }

  if (url.origin !== self.location.origin) return;

  if (isDataRequest(url)) {
    event.respondWith(networkFirst(request, DATA_CACHE, dataCacheKey(request.url)));
    return;
  }

  // Navigations: fresh HTML when online, cached shell when not.
  if (request.mode === 'navigate') {
    event.respondWith(
      networkFirst(request, SHELL_CACHE).catch(async () => {
        const cache = await caches.open(SHELL_CACHE);
        return (await cache.match('./index.html')) || (await cache.match('./')) || Response.error();
      })
    );
    return;
  }

  event.respondWith(cacheFirst(request, SHELL_CACHE).catch(() => fetch(request)));
});
