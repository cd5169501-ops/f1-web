// Service worker mínimo para que la app se pueda instalar y abra sin conexión.
// Los datos se piden primero a la red para no quedar con horarios viejos.

const CACHE = 'f1-2026-v1';
const ARCHIVOS_BASE = [
  './',
  './index.html',
  './manifest.json',
  './data/temporada-2026.json',
  './data/novedades.json',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ARCHIVOS_BASE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(
        claves.filter((clave) => clave !== CACHE).map((clave) => caches.delete(clave))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evento) => {
  const pedido = evento.request;

  if (pedido.method !== 'GET') return;

  const url = new URL(pedido.url);
  if (url.origin !== self.location.origin) return;

  // Red primero para tener siempre la última versión; la caché es el respaldo
  // cuando no hay conexión (o cuando el servidor responde con un error).
  evento.respondWith(
    fetch(pedido)
      .then((respuesta) => {
        if (respuesta && respuesta.ok) {
          const copia = respuesta.clone();
          caches.open(CACHE).then((cache) => cache.put(pedido, copia));
          return respuesta;
        }

        return caches.match(pedido).then((guardado) => guardado || respuesta);
      })
      .catch(() => {
        return caches.match(pedido).then((guardado) => {
          return guardado || new Response('Sin conexión', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' }
          });
        });
      })
  );
});
