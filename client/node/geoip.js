'use strict';
// Item 13, launch side. The lookup lives once, in Python (camoucrome.geoip: a DB-IP Lite or GeoLite2-layout .mmdb, the
// zone from the coordinates); Node spawns it. IP Geolocation by DB-IP.
const childProcess = require('child_process');
const net = require('net');
const tls = require('tls');

const ECHO_URLS = ['https://api.ipify.org', 'https://checkip.amazonaws.com', 'https://icanhazip.com', 'https://ifconfig.co/ip'];
const TIMEOUT_MS = 5000;

function dechunk(buf) {
  let out = '';
  for (let rest = buf; ;) {
    const nl = rest.indexOf('\r\n');
    if (nl < 0) return out;
    const n = parseInt(rest.slice(0, nl), 16);
    if (!n) return out;
    out += rest.slice(nl + 2, nl + 2 + n);
    rest = rest.slice(nl + 2 + n + 2);
  }
}

// One GET through the proxy's CONNECT, written by hand (decided 2026-10-24: no new dependency). Node's fetch does not
// use a proxy. Resolves to the response body.
function getViaConnect(proxy, target, timeoutMs = TIMEOUT_MS) {
  const p = new URL(proxy.server);
  const t = new URL(target);
  const port = Number(t.port) || (t.protocol === 'https:' ? 443 : 80);
  const authority = `${t.hostname}:${port}`;
  const auth = proxy.username
    ? `Proxy-Authorization: Basic ${Buffer.from(`${proxy.username}:${proxy.password || ''}`).toString('base64')}\r\n` : '';
  return new Promise((resolve, reject) => {
    const sock = net.connect(Number(p.port) || 80, p.hostname);
    const fail = (e) => { sock.destroy(); reject(e instanceof Error ? e : new Error(String(e))); };
    sock.setTimeout(timeoutMs, () => fail('timeout'));
    sock.on('error', fail);
    let head = '';
    const onHead = (chunk) => {
      head += chunk.toString('latin1');
      const end = head.indexOf('\r\n\r\n');
      if (end < 0) return;
      sock.off('data', onHead);
      const status = head.split(' ')[1];
      if (status !== '200') return fail(`proxy answered CONNECT with ${status}`);
      const stream = t.protocol === 'https:' ? tls.connect({ socket: sock, servername: t.hostname }) : sock;
      stream.on('error', fail);
      const chunks = [];
      stream.on('data', (c) => chunks.push(c));
      stream.on('end', () => {
        const raw = Buffer.concat(chunks).toString('latin1');
        const sep = raw.indexOf('\r\n\r\n');
        const resHead = raw.slice(0, sep);
        if (!/^HTTP\/1\.[01] 200/.test(resHead)) return fail(`echo service answered ${resHead.split(' ')[1]}`);
        const body = raw.slice(sep + 4);
        resolve(/transfer-encoding:\s*chunked/i.test(resHead) ? dechunk(body) : body);
      });
      stream.write(`GET ${t.pathname}${t.search} HTTP/1.1\r\nHost: ${t.host}\r\nConnection: close\r\nUser-Agent: camoucrome\r\n\r\n`);
    };
    sock.on('data', onHead);
    sock.on('connect', () => sock.write(`CONNECT ${authority} HTTP/1.1\r\nHost: ${authority}\r\n${auth}\r\n`));
  });
}

// The address the world sees: an echo service asked through the proxy (undefined = direct, with fetch).
async function exitIp(proxy, urls = ECHO_URLS) {
  const errors = [];
  for (const url of urls) {
    try {
      const body = proxy
        ? await getViaConnect(proxy, url)
        : await (await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) })).text();
      const ip = body.trim();
      if (net.isIP(ip)) return ip;
      errors.push(`${url}: not an address`);
    } catch (e) {
      errors.push(`${url}: ${e.message || e}`);
    }
  }
  throw new Error(`no echo service answered (${errors.join('; ')})`);
}

// Warnings about the config's timezone:id against the exit address. Never throws, never changes the config.
// `run(python, args)` and `echo(proxy)` are the test seams.
async function checkGeoip({ config, proxy, exitIp: given, geoip, python = 'python3', run = defaultRun, echo = exitIp }) {
  let cfg = config;
  // a malformed config is launch's to report, as in the Go client
  try { if (typeof cfg === 'string') cfg = JSON.parse(cfg); } catch { return []; }
  const zone = cfg && typeof cfg === 'object' ? cfg['timezone:id'] : undefined;
  if (!zone) return [];
  const cannot = (why) => [`timezone:id ${zone} could not be checked against the exit IP: ${why}`];
  let ip = given;
  if (!ip) {
    try { ip = await echo(proxy); } catch (e) { return cannot(e.message); }
  }
  let out;
  try {
    out = run(python, ['-m', 'camoucrome.geoip', '--ip', ip, '--db', geoip, '--check-zone', zone]);
  } catch (e) {
    return cannot(e.message);
  }
  let r;
  try { r = JSON.parse(out); } catch { return cannot(`camoucrome.geoip printed no JSON (is camoucrome[geoip] installed for ${python}?)`); }
  if (!r || typeof r !== 'object') return cannot(`camoucrome.geoip printed no JSON (is camoucrome[geoip] installed for ${python}?)`);
  if (r.error) return cannot(r.error);
  return r.warning ? [r.warning] : [];
}

function defaultRun(python, args) {
  const p = childProcess.spawnSync(python, args, { encoding: 'utf8', timeout: 15000 });
  if (p.error) throw p.error; // ENOENT or ETIMEDOUT, both become a cannot-warning; exit 2 still prints {"error": ...} on stdout
  return p.stdout;
}

module.exports = { ECHO_URLS, exitIp, getViaConnect, checkGeoip };
