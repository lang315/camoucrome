'use strict';
// A real browser through a real local proxy. Skipped unless CAMOU_TEST_CHROME names a Chrome executable.
// launch({ proxy }) once did nothing at all: the launcher drops Playwright's default argv, and --proxy-server is
// one of its defaults, so a user's traffic went out on their real address. The fixture counts what reaches it.
const assert = require('node:assert/strict');
const http = require('http');
const { test } = require('node:test');
const c = require('..');

const EXE = process.env.CAMOU_TEST_CHROME;
let chromium;
try { ({ chromium } = require('patchright')); } catch { /* no driver installed: skipped below */ }
const skip = !EXE || !chromium ? 'set CAMOU_TEST_CHROME and install patchright' : false;

// 407 until Proxy-Authorization arrives; then 200 for a GET and 502 for a CONNECT. seen = [[method, authenticated]].
function countingProxy() {
  const seen = [];
  const challenge = 'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="t"\r\nContent-Length: 0\r\n\r\n';
  const srv = http.createServer((q, r) => {
    const authed = Boolean(q.headers['proxy-authorization']);
    if (q.url.includes('example.test')) seen.push([q.method, authed]);
    if (!authed) { r.writeHead(407, { 'Proxy-Authenticate': 'Basic realm="t"', 'Content-Length': 0 }); return r.end(); }
    r.writeHead(200, { 'Content-Type': 'text/html' });
    r.end('<title>via-proxy</title>ok');
  });
  srv.on('connect', (q, sock) => {
    const authed = Boolean(q.headers['proxy-authorization']);
    if (q.url.includes('example.test')) seen.push(['CONNECT', authed]);
    sock.end(authed ? 'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n' : challenge);
  });
  return new Promise((res) => srv.listen(0, '127.0.0.1', () =>
    res({ seen, url: `http://127.0.0.1:${srv.address().port}`, close: () => srv.close() })));
}

async function visit(url, opts) {
  const ctx = await c.launch(chromium, EXE, { headless: true, ...opts });
  try {
    const page = await ctx.newPage();
    try { await page.goto(url, { timeout: 15000 }); return await page.title(); } catch (e) { return `ERR ${String(e.message).split('\n')[0]}`; }
  } finally { await ctx.close(); }
}

test('the proxy option reaches the proxy and authenticates', { skip }, async () => {
  const p = await countingProxy();
  try {
    const title = await visit('http://example.test/', { proxy: { server: p.url, username: 'u', password: 'p' } });
    assert.equal(title, 'via-proxy');
    assert.ok(p.seen.some(([m, a]) => m === 'GET' && !a) && p.seen.some(([m, a]) => m === 'GET' && a), JSON.stringify(p.seen));
  } finally { p.close(); }
});

test('https goes through CONNECT', { skip }, async () => {
  const p = await countingProxy();
  try {
    await visit('https://example.test/', { proxy: { server: p.url, username: 'u', password: 'p' } });
    assert.ok(p.seen.some(([m, a]) => m === 'CONNECT' && a), JSON.stringify(p.seen));
  } finally { p.close(); }
});

test('without the option nothing reaches the proxy', { skip }, async () => {
  const p = await countingProxy();
  try {
    assert.match(await visit('http://example.test/', {}), /^ERR/);
    assert.deepEqual(p.seen, []);
  } finally { p.close(); }
});
