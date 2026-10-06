// Prueba de carga de la API y el MCP. Ver "Pruebas de carga" en el README.
// BASE=directo → api:8000 y mcp:8000 (capacidad de la app, sin caché ni rate limit)
// BASE=nginx   → nginx/api y nginx/mcp (ruta pública, con caché y límites por IP)
//   Cada VU manda su propia IP en X-Forwarded-For, como llega por Cloudflare; IPS=n simula n IPs compartidas
//   (p. ej. IPS=3 para muchos usuarios de ChatGPT saliendo por pocas IPs de OpenAI).
// Cada VU es un usuario que piensa PAUSA segundos en promedio entre iteraciones; PAUSA=0 es estrés puro.
import http from 'k6/http';
import { check, sleep } from 'k6';

const NGINX = __ENV.BASE === 'nginx';
const API = NGINX ? 'http://nginx/api' : 'http://api:8000';
const MCP = NGINX ? 'http://nginx/mcp' : 'http://mcp:8000/mcp';
const DS = 'eic2025_localidades';
const IPS = Number(__ENV.IPS) || 0;
const PAUSA = Number(__ENV.PAUSA ?? 2);

const umbrales = ['p(95)<500', 'p(99)<1500'].map((threshold) => ({ threshold, abortOnFail: false }));

export const options = {
  scenarios: {
    rampa: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: 200 },
        { duration: '2m', target: 200 },
        { duration: '2m', target: 1000 },
        { duration: '2m', target: 1000 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  // Un threshold por tag hace que el resumen muestre los percentiles de api y mcp por separado.
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: false }],
    'http_req_duration{tipo:api}': umbrales,
    'http_req_duration{tipo:mcp}': umbrales,
    'checks{tipo:api}': ['rate>0.99'],
    'checks{tipo:mcp}': ['rate>0.99'],
  },
};

const azar = (xs) => xs[Math.floor(Math.random() * xs.length)];

// Todos los indicadores y municipios reales, para que casi ninguna llamada caiga en caché.
export function setup() {
  const ind = http.get(`${API}/datasets/${DS}/indicadores`).json().map((i) => i.codigo);
  const mun = http.get(`${API}/datasets/${DS}/geografias?nivel=municipio&limit=10000`).json().items
    .map((g) => ({ cvegeo: g.cvegeo, ent: g.cve_ent, texto: `${g.nombre}, ${g.nom_ent}` }));
  return { ind, mun };
}

const PETICIONES_API = [
  (d, m) => `/datasets/${DS}/datos?indicador=${azar(d.ind)}&cvegeo=${m.cvegeo}`,
  (d, m) => `/datasets/${DS}/ranking?indicador=${azar(d.ind)}&nivel=municipio&cve_ent=${m.ent}`,
  (d, m) => `/datasets/${DS}/perfil/${m.cvegeo}`,
  (d, m) => `/ubicar?q=${encodeURIComponent(m.texto)}`,
];

const TOOLS_MCP = [
  (d, m) => ['ubicar_lugar', { texto: m.texto }],
  (d, m) => ['obtener_datos', { dataset: DS, indicadores: [azar(d.ind)], cvegeo: [m.cvegeo] }],
  (d, m) => ['ranking', { indicador: azar(d.ind), nivel: 'municipio', cve_ent: m.ent }],
  (d, m) => ['perfil_lugar', { cvegeo: m.cvegeo }],
];

export default function (d) {
  const lugar = azar(d.mun);
  const n = IPS ? (__VU % IPS) : __VU;
  const ip = { 'X-Forwarded-For': `198.18.${n >> 8}.${n & 255}` };  // rango de pruebas, fuera de las redes confiables
  const tags = { tipo: 'api' };
  const r = http.get(API + azar(PETICIONES_API)(d, lugar), { headers: ip, tags });
  check(r, { 'api 200': (res) => res.status === 200 }, tags);

  const [name, args] = azar(TOOLS_MCP)(d, lugar);
  const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name, arguments: args } });
  const tagsMcp = { tipo: 'mcp', tool: name };
  const m = http.post(MCP, body, { headers: { ...ip, 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' }, tags: tagsMcp });
  check(m, {
    'mcp 200': (res) => res.status === 200,
    'mcp sin error': (res) => {
      const j = res.status === 200 ? res.json() : null;
      return !!j && !j.error && !j.result.isError;
    },
  }, { tipo: 'mcp', tool: name });

  if (PAUSA) sleep(PAUSA * (0.5 + Math.random()));
}
