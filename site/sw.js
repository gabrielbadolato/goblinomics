// Deixa o site abrir como aplicativo mesmo sem internet. A rede vem sempre primeiro: com conexão,
// nada muda; sem ela, valem a página e os últimos dados que este aparelho já tinha baixado.
const CACHE = "goblinomics-v1";
const CASCA = ["./", "manifest.webmanifest", "icone-192.png", "icone-512.png"];

self.addEventListener("install", e => e.waitUntil(
  caches.open(CACHE).then(c => c.addAll(CASCA)).then(() => self.skipWaiting())));

self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(nomes => Promise.all(nomes.filter(n => n !== CACHE).map(n => caches.delete(n))))
    .then(() => self.clients.claim())));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // O histórico é um arquivo por item e o addon é um download: não vale guardar.
  const guardar = !/\/dados\/hist\/|\/addon\//.test(url.pathname);
  // Sem a parte depois do "?", para "index.html?v=2" e "index.html" serem a mesma cópia.
  const chave = url.origin + url.pathname;
  e.respondWith(fetch(e.request).then(resposta => {
    if (resposta.ok && guardar) {
      const copia = resposta.clone();
      e.waitUntil(caches.open(CACHE).then(c => c.put(chave, copia)));
    }
    return resposta;
  }).catch(() => caches.match(chave).then(guardada => guardada || Response.error())));
});
