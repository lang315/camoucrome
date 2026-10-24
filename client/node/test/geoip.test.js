'use strict';
const assert = require('node:assert/strict');
const http = require('http');
const net = require('net');
const { test } = require('node:test');
const c = require('..');
const g = require('../geoip');

const cfg = { 'timezone:id': 'Asia/Tokyo' };
const seams = (out, ip = '192.0.2.5') => {
  const calls = [];
  return { calls, run: (py, args) => { calls.push([py, ...args]); if (out instanceof Error) throw out; return out; }, echo: async () => ip };
};

test('checkGeoip surfaces the modules warning and passes the right arguments', async () => {
  const s = seams('{"timezone":"America/New_York","warning":"contradicts"}');
  assert.deepEqual(await g.checkGeoip({ config: cfg, geoip: '/db.mmdb', python: 'py', ...s }), ['contradicts']);
  assert.deepEqual(s.calls, [['py', '-m', 'camoucrome.geoip', '--ip', '192.0.2.5', '--db', '/db.mmdb', '--check-zone', 'Asia/Tokyo']]);
});

test('checkGeoip is quiet on a match and has nothing to check without a zone', async () => {
  assert.deepEqual(await g.checkGeoip({ config: cfg, geoip: '/db', ...seams('{"warning":null}') }), []);
  const s = seams('{}');
  assert.deepEqual(await g.checkGeoip({ config: { a: 1 }, geoip: '/db', ...s }), []);
  assert.deepEqual(await g.checkGeoip({ config: '{"timezone:id":"Asia/Tokyo"}', geoip: '/db', ...seams('{"warning":null}') }), []);
  assert.equal(s.calls.length, 0);
});

test('checkGeoip warns instead of failing when it cannot tell', async () => {
  const cannot = async (opts, re) => {
    const [m] = await g.checkGeoip({ config: cfg, geoip: '/db', ...opts });
    assert.match(m, /could not be checked/);
    assert.match(m, re);
  };
  await cannot({ ...seams(''), echo: async () => { throw new Error('no echo service answered'); } }, /no echo service/);
  await cannot(seams('{"error":"192.0.2.5 is not in the database"}'), /not in the database/);
  await cannot(seams('Traceback ...'), /no JSON/);
  await cannot(seams(new Error('spawn python3 ENOENT')), /ENOENT/);
});

test('a given exit IP skips the echo request', async () => {
  const s = seams('{"warning":null}');
  s.echo = async () => { throw new Error('must not be asked'); };
  await g.checkGeoip({ config: cfg, geoip: '/db', exitIp: '192.0.2.9', ...s });
  assert.equal(s.calls[0][4], '192.0.2.9');
});

test('launch warns before it touches the driver, and does nothing without the option', async () => {
  const said = [];
  const ctx = { on: () => {}, close: async () => {} };
  const chromium = { launchPersistentContext: async () => ctx };
  // geoip.js is required lazily by launch; stub its python through a fake interpreter name that cannot exist
  await c.launch(chromium, '/x/chrome', { config: cfg, geoip: '/db', exitIp: '192.0.2.5', python: 'camoucrome-no-such-python', warn: (m) => said.push(m) });
  assert.equal(said.length, 1);
  assert.match(said[0], /could not be checked/);
  await c.launch(chromium, '/x/chrome', { config: cfg, warn: (m) => said.push(m) });
  assert.equal(said.length, 1);
});

test('an invalid proxy throws its own error before any geoip check runs', async () => {
  const said = [];
  const chromium = { launchPersistentContext: async () => { throw new Error('must not launch'); } };
  // a check that ran would warn (no such interpreter), so an empty `said` proves none ran
  await assert.rejects(c.launch(chromium, '/x/chrome', { proxy: { server: 'http://u:p@h:1' }, geoip: '/db', config: cfg,
    exitIp: '192.0.2.5', python: 'camoucrome-no-such-python', warn: (m) => said.push(m) }), /proxy/);
  assert.deepEqual(said, []);
});

// A proxy that tunnels every CONNECT to one local server, whatever the name: 407 until Proxy-Authorization arrives.
function connectProxy(echoPort, { auth = false } = {}) {
  const seen = [];
  const srv = net.createServer((sock) => {
    let buf = '';
    sock.on('error', () => {});
    sock.on('data', function onData(d) {
      buf += d.toString('latin1');
      if (!buf.includes('\r\n\r\n')) return;
      sock.off('data', onData);
      const authed = /proxy-authorization: basic /i.test(buf);
      seen.push([buf.split('\r\n')[0], authed]);
      if (auth && !authed) return sock.end('HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n');
      const up = net.connect(echoPort, '127.0.0.1', () => sock.write('HTTP/1.1 200 Connection established\r\n\r\n'));
      up.on('error', () => sock.destroy());
      sock.pipe(up); up.pipe(sock);
    });
  });
  return new Promise((res) => srv.listen(0, '127.0.0.1', () => res({ seen, server: `http://127.0.0.1:${srv.address().port}`, close: () => srv.close() })));
}

function echoServer(body, headers = {}) {
  const srv = http.createServer((q, r) => { r.writeHead(200, headers); r.end(body); });
  return new Promise((res) => srv.listen(0, '127.0.0.1', () => res({ port: srv.address().port, close: () => srv.close() })));
}

test('exitIp tunnels through CONNECT with credentials and reads the echoed address', async () => {
  const echo = await echoServer('203.0.113.9\n');
  const p = await connectProxy(echo.port, { auth: true });
  try {
    const ip = await g.exitIp({ server: p.server, username: 'u', password: 'p@ss' }, ['http://echo.test/']);
    assert.equal(ip, '203.0.113.9');
    assert.deepEqual(p.seen, [['CONNECT echo.test:80 HTTP/1.1', true]]); // credentials go with the first CONNECT: no 407 round
  } finally { p.close(); echo.close(); }
});

test('exitIp reads a chunked answer and gives up on garbage and on a refused CONNECT', async () => {
  const echo = await echoServer('2001:db8::7', { 'Transfer-Encoding': 'chunked' });
  const p = await connectProxy(echo.port);
  try {
    assert.equal(await g.exitIp({ server: p.server }, ['http://echo.test/']), '2001:db8::7');
  } finally { p.close(); echo.close(); }
  const junk = await echoServer('<html>blocked</html>');
  const p2 = await connectProxy(junk.port);
  try {
    await assert.rejects(g.exitIp({ server: p2.server }, ['http://a.test/', 'http://b.test/']), /no echo service answered.*not an address/);
  } finally { p2.close(); junk.close(); }
  const p3 = await connectProxy(1, { auth: true });
  try {
    await assert.rejects(g.exitIp({ server: p3.server }, ['http://a.test/']), /407/);
  } finally { p3.close(); }
});
