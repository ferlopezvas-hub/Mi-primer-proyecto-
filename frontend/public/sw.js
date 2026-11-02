/* Service worker de SPORT AI PREDICTOR: notificaciones push + caché del "app shell". */
const CACHE = "sportai-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Navegación: red primero, caché como respaldo (la app abre aunque no haya conexión).
// Las llamadas a la API nunca se cachean: los datos deportivos deben ser frescos.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api") || url.origin !== self.location.origin) return;
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() => caches.match("/index.html")));
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })),
    );
  }
});

self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch { data = { title: "SPORT AI", body: e.data && e.data.text() }; }
  const title = data.title || "SPORT AI PREDICTOR";
  e.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    tag: data.tag,            // agrupa por partido: una notificación nueva sustituye a la anterior
    renotify: true,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url: data.url || "/", id: data.id },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) {
      if ("focus" in c) { c.navigate(target); return c.focus(); }
    }
    return self.clients.openWindow(target);
  }));
});
