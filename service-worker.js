const cacheName='srt-fix-cache-v1';
const assets=['/','/index.html','/styles.css','/app.js','/manifest.json'];
self.addEventListener('install',evt=>{evt.waitUntil(caches.open(cacheName).then(cache=>cache.addAll(assets)));self.skipWaiting();});
self.addEventListener('activate',evt=>{evt.waitUntil(caches.keys().then(keys=>Promise.all(keys.map(k=>k!==cacheName?caches.delete(k):null))));self.clients.claim();});
self.addEventListener('fetch',evt=>{evt.respondWith(caches.match(evt.request).then(r=>r||fetch(evt.request)));});
