/* Offline support for the phone site.
   - app.bin?v=<hash> (the encrypted app, ~6 MB): cache-first; the URL changes on every update, old copies are pruned.
   - everything else of our own (the gate page, icons, manifest): network-first, falling back to the cache when
     offline or when the network takes more than 3.5 s and a cached copy exists.
   Cross-origin requests (web fonts) are left to the browser. */
const CACHE = "isn-v1";
const isBin = u => /\/app\.bin$/.test(u.pathname);

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith("isn-") && k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function prune(c, keepUrl) {
  for (const k of await c.keys()) if (isBin(new URL(k.url)) && k.url !== keepUrl) await c.delete(k);
}
async function cacheFirst(e, req) {
  const c = await caches.open(CACHE);
  const hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok) {
    const copy = res.clone();
    e.waitUntil(c.put(req, copy).then(() => prune(c, req.url)).catch(() => {}));
  }
  return res;
}
async function fromCache(c, req) {
  return (await c.match(req)) || (req.mode === "navigate" ? await c.match(new URL("./", self.registration.scope).href) : undefined);
}
async function networkFirst(req, net, cp) {
  const c = await cp;
  let timer;
  const late = new Promise(r => { timer = setTimeout(r, 3500, "late"); });
  try {
    const first = await Promise.race([net, late]);
    if (first !== "late") return first;
    const hit = await fromCache(c, req);
    return hit || await net;
  } catch (err) {
    const hit = await fromCache(c, req);
    if (hit) return hit;
    throw err;
  } finally { clearTimeout(timer); }
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (isBin(url)) { e.respondWith(cacheFirst(e, req)); return; }
  const cp = caches.open(CACHE);
  const net = fetch(req).then(async res => {
    if (res.ok && res.type === "basic") { try { await (await cp).put(req, res.clone()); } catch (_) {} }
    return res;
  });
  e.waitUntil(net.catch(() => {}));
  e.respondWith(networkFirst(req, net, cp));
});
