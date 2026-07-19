// Service worker — shell dell'app in cache, dati sempre dalla rete (fallback cache)
const VER = 'nh-v4';
const SHELL = ['app.html', 'js/app-core.js', 'manifest.webmanifest', 'icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VER).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  // dati (GitHub API/raw): solo rete — l'app ha già il suo fallback in localStorage
  if (url.hostname.includes('github')) return;
  // shell e asset: stale-while-revalidate
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(hit => {
      const net = fetch(e.request).then(r => {
        if (r.ok) caches.open(VER).then(c => c.put(e.request, r.clone()));
        return r;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
