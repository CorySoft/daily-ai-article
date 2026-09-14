#!/usr/bin/env node
// wechat-publish.js — 客户端发布脚本（跨平台，无需 PHP，仅需 Node.js）
// 依赖：Node.js 12+（内置 crypto / http / https，无任何 npm 包）
//
// 用法：
//   node scripts/wechat-publish.js [选项]
//
// 选项：
//   --config <path>    配置文件（默认 scripts/client_config.json，存在则加载）
//   --server <url>     中转服务器地址，如 https://your-host
//   --secret <str>     共享密钥（与服务器 config.php 一致）
//   --appid <str>      微信公众号 AppID
//   --appsecret <str>  微信公众号 AppSecret
//   --file <path>      JSON 请求体文件，如 {"draft":true,"articles":[...]}
//   --endpoint <path>  API 路径，默认 /publish
//   --method <verb>    HTTP 方法（默认 POST，GET 路由用 --method GET）
//   --unlock-password <str>  阿贝云(abeiyun)调试域名门禁密码（config.unlock_password）
//
// 阿贝云调试域名自动解锁：若服务器返回门禁页（系统域名_网站调试域名），
// 且配置了 unlock_password，则自动调用解锁接口获取令牌并写 cookie 后重试一次。
//
// 请求体也可从 stdin 传入：echo '{"count":5}' | node scripts/wechat-publish.js --endpoint /draft/list
//
// 凭证加密：AES-256-CBC + HMAC-SHA256（密钥 = sha256(shared_secret)），
// 格式 v1:<iv_hex>:<mac_hex>:<ciphertext_base64>，服务器临时解密、不落盘。

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const { spawn } = require('child_process');

// ---- 参数解析 ----
const opts = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a.startsWith('--')) {
    const key = a.slice(2);
    const val = argv[++i];
    if (val === undefined) {
      console.error(`缺少值: --${key}`);
      process.exit(1);
    }
    opts[key] = val;
  }
}

// ---- 可选的本机配置（按优先级：--config > 本地 client_config.json > 全局配置）----
let config = {};
const GLOBAL_CONFIG = path.join(
  process.env.HOME || process.env.USERPROFILE || '~',
  '.config', 'wechat-publisher', 'client_config.json'
);
const localConfig = path.join(__dirname, 'client_config.json');
const configPath = opts.config || (fs.existsSync(localConfig) ? localConfig : GLOBAL_CONFIG);
if (fs.existsSync(configPath)) {
  try {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (e) {
    console.error(`配置文件解析失败: ${configPath} — ${e.message}`);
    process.exit(1);
  }
}

const server = opts.server || config.server || '';
const secret = opts.secret || config.shared_secret || '';
const appId = opts.appid || config.app_id || '';
const appSecret = opts.appsecret || config.app_secret || '';
const endpoint = opts.endpoint || '/publish';
const httpMethod = (opts.method || 'POST').toUpperCase();
const unlockPassword = opts['unlock-password'] || config.unlock_password || '';

for (const [name, val] of [['server', server], ['secret', secret], ['appid', appId], ['appsecret', appSecret]]) {
  if (!val) {
    console.error(`缺少必要参数: ${name}（用 --${name} 传入或在 client_config.json 配置）`);
    process.exit(1);
  }
}

// ---- 读取请求体（--file 或 stdin）----
let body = '';
if (opts.file) {
  try {
    body = fs.readFileSync(opts.file, 'utf8');
  } catch (e) {
    console.error(`读取文件失败: ${opts.file} — ${e.message}`);
    process.exit(1);
  }
} else {
  body = fs.readFileSync(0, 'utf8'); // stdin
}
body = body.trimEnd();
if (!body) {
  console.error('请求体为空（--file <path> 或从 stdin 传入 JSON）');
  process.exit(1);
}

// ---- 加密凭证（AES-256-CBC + HMAC-SHA256）----
const keyHex = crypto.createHash('sha256').update(secret).digest('hex');
const iv = crypto.randomBytes(16);
const credJson = JSON.stringify({ app_id: appId, app_secret: appSecret });
const cipher = crypto.createCipheriv('aes-256-cbc', Buffer.from(keyHex, 'hex'), iv);
const ct = Buffer.concat([cipher.update(credJson, 'utf8'), cipher.final()]).toString('base64');
const mac = crypto.createHmac('sha256', keyHex).update(iv.toString('hex') + ct).digest('hex');
const credPayload = `v1:${iv.toString('hex')}:${mac}:${ct}`;

// ---- 注入 credentials 字段（安全地解析 JSON 并重新序列化）----
let parsed;
try {
  parsed = JSON.parse(body);
} catch (e) {
  console.error(`JSON 解析失败: ${e.message}`);
  process.exit(1);
}
parsed.credentials = credPayload;
body = JSON.stringify(parsed);

// ---- 发送 ----
const url = new URL(server + endpoint);
const isHttps = url.protocol === 'https:';
const transport = isHttps ? https : http;

// 阿贝云调试域名解锁中心接口
const UNLOCK_API = 'https://api.abeiyun.com/www/break.php';

// 从 XML 响应中提取解锁令牌（errMsg，即调试域名本身），失败返回 null
function parseToken(out) {
  const m = String(out).match(/<errMsg>([^<]*)<\/errMsg>/);
  return m ? m[1].trim() : null;
}

// 调用阿贝云解锁接口，返回令牌，失败返回 null。
// 优先用 node https（跨平台、无依赖）；个别环境 node 到阿贝云 TLS/POST 会被重置，
// 此时回退到 curl 兜底，保证任意机器都能自动解锁。
function unlockDebugDomain(hostname) {
  return new Promise((resolve) => {
    const u = new URL(UNLOCK_API);
    const path = `/www/break.php?cmd=visit_sysdomain&password=${encodeURIComponent(unlockPassword)}`;
    const headers = {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Referer': `http://${hostname}/`,
    };
    const r = https.request({ hostname: u.hostname, path, method: 'POST', headers }, (res) => {
      let out = '';
      res.on('data', (c) => { out += c; });
      res.on('end', () => resolve(parseToken(out)));
    });
    r.on('error', () => resolve(null));
    r.setTimeout(10000, () => { r.destroy(); });
    r.write('x=1');
    r.end();
  }).then((token) => {
    if (token) return token;
    // curl 兜底
    return new Promise((resolve) => {
      const child = spawn('curl', [
        '-s', '-m', '15', '-X', 'POST', `${UNLOCK_API}?cmd=visit_sysdomain&password=${encodeURIComponent(unlockPassword)}`,
        '-H', 'Content-Type: application/x-www-form-urlencoded',
        '-H', `Referer: http://${hostname}/`,
        '-d', 'x=1',
      ]);
      let out = '';
      child.stdout.on('data', (c) => { out += c; });
      child.stderr.on('data', () => {});
      child.on('close', () => resolve(parseToken(out)));
      child.on('error', () => resolve(null));
    });
  });
}

// 发送一次请求，返回 { statusCode, body }，网络错误/超时 reject。
// 带 socket 超时：超过 REQUEST_TIMEOUT_MS 无数据即 destroy 并 reject，
// 防止 Byethost 这类慢主机一次挂住整个 run（且由主循环重试，不会直接致命）。
const REQUEST_TIMEOUT_MS = 120000;
function sendRequest(cookieHeader) {
  return new Promise((resolve, reject) => {
    const headers = {
      'Content-Type': 'application/json',
      'X-Shared-Secret': secret,
      'Content-Length': Buffer.byteLength(body),
    };
    if (cookieHeader) {
      headers['Cookie'] = cookieHeader;
    }
    // Byethost 门禁放行固定走 "?i=1"（解锁 cookie 后需带该参数重试原请求才生效）。
    // 带 cookie 的请求一律附加；非 Byethost 后端会忽略多余 query。
    const gateNav = (cookieHeader ? ((url.search ? '&' : '?') + 'i=1') : '');
    const reqOpts = {
      hostname: url.hostname,
      path: url.pathname + url.search + gateNav,
      method: httpMethod,
      headers,
    };
    if (url.port) {
      reqOpts.port = Number(url.port);
    }
    // 防 promise 二次 settle：timeout/error/end/aborted 多路径只认第一次
    let settled = false;
    const once = (fn, val) => {
      if (settled) return;
      settled = true;
      fn(val);
    };
    const req = transport.request(reqOpts, (res) => {
      let out = '';
      res.on('data', (c) => { out += c; });
      res.on('end', () => { once(resolve, { statusCode: res.statusCode, body: out }); });
      res.on('aborted', () => once(reject, new Error('响应被服务端中断 (aborted)')));
      res.on('error', (e) => once(reject, e));
    });
    req.on('error', (e) => once(reject, e));
    req.setTimeout(REQUEST_TIMEOUT_MS, () => {
      req.destroy(new Error(`请求超时（${REQUEST_TIMEOUT_MS / 1000}s 无数据），已中止`));
    });
    req.write(body);
    req.end();
  });
}

// 服务器返回的 body 是否表示调用失败（{error: ...}）。成功形如 {"ok":true,...}
function responseHasError(body) {
  try {
    const parsed = JSON.parse(body);
    if (parsed && typeof parsed === 'object' && parsed.error) {
      return true;
    }
  } catch (e) {
    // 非 JSON 响应：非 2xx 即视为失败
    return true;
  }
  return false;
}

// ---- Byethost 反爬门禁破解 ----
// Byethost 免费空间在 openresty 前挡了一层 JS 门禁：返回
//   <script src="/aes.js"></script>
//   var a=toNumbers("..."),b=toNumbers("..."),c=toNumbers("...");
//   document.cookie="__test="+toHex(slowAES.decrypt(c,2,a,b))+"; ..." ; location.href="?i=1"
// 其中 slowAES.decrypt(c,2,a,b) = AES-128-CBC(密文c, 密钥a, IV b, 无填充)。
// 客户端无法执行 JS，这里用 Node crypto 直接解密出 __test 并作为 cookie 重试即可绕过。
function isByethostGate(body) {
  return typeof body === 'string'
    && body.includes('slowAES')
    && body.includes('toNumbers')
    && body.includes('__test');
}

function solveByethostCookie(body) {
  const m = String(body).match(
    /\ba=toNumbers\("([0-9a-f]{32})"\),b=toNumbers\("([0-9a-f]{32})"\),c=toNumbers\("([0-9a-f]+)"\)/
  );
  if (!m) return null;
  try {
    const decipher = crypto.createDecipheriv(
      'aes-128-cbc',
      Buffer.from(m[1], 'hex'),
      Buffer.from(m[2], 'hex')
    );
    decipher.setAutoPadding(false);
    const token = Buffer.concat([
      decipher.update(Buffer.from(m[3], 'hex')),
      decipher.final(),
    ]).toString('hex');
    return '__test=' + token;
  } catch (e) {
    return null;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

(async () => {
  let cookie = '';

  // 阿贝云调试域名：若配置了门禁密码，请求前先自动解锁拿 cookie，跳过门禁
  if (unlockPassword && (url.hostname.endsWith('abeiyun.cn') || url.hostname.endsWith('host109.abeiyun.cn'))) {
    const token = await unlockDebugDomain(url.hostname);
    if (token) {
      cookie = 'zhujiwusysdomain=' + encodeURIComponent(token);
    }
  }

  // 网络/服务器瞬时错误自动重试，最多 3 次；
  // Byethost 门禁解锁不消耗重试次数，但总次数受限，防止空转。
  const MAX_ATTEMPTS = 3;
  const MAX_GATE_SOLVES = 3;
  let lastBody = '';
  let lastStatus = null;
  let lastNetworkError = null;
  let gateSolves = 0;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; ) {
    let resp;
    try {
      resp = await sendRequest(cookie);
    } catch (e) {
      // 网络错误（超时/断连/解析失败）也进重试，而不是直接 exit：
      // 避免慢主机"慢但成功"被误杀成"必失败"
      lastNetworkError = e;
      console.log(`[网络错误 attempt ${attempt}/${MAX_ATTEMPTS}] ${e.message}`);
      if (attempt < MAX_ATTEMPTS) {
        await sleep(3000);
      }
      attempt++;
      continue;
    }
    lastBody = resp.body;
    lastStatus = resp.statusCode;
    if (attempt > 1) {
      console.log(`[retry ${attempt - 1}/${MAX_ATTEMPTS - 1}] 服务器仍返回错误，稍后重试...`);
    }
    // Byethost 反爬门禁：解密 __test 并带上重试（不消耗重试次数，但总次数受限）
    if (isByethostGate(resp.body)) {
      const gateCookie = solveByethostCookie(resp.body);
      if (gateCookie) {
        cookie = gateCookie;
        gateSolves++;
        console.log(`Byethost 门禁已解锁（${Math.min(gateSolves, MAX_GATE_SOLVES)}/${MAX_GATE_SOLVES}），携带 __test cookie 重试...`);
        if (gateSolves > MAX_GATE_SOLVES) {
          console.error(`Byethost 门禁尝试 ${gateSolves} 次仍未通过，放弃。`);
          console.error(`[最后一次响应] ${resp.body}`);
          process.exitCode = 1;
          break;
        }
        attempt = 0; // 门禁成功不计入重试次数
        continue;
      }
      console.log('Byethost 门禁出现但无法解出 __test，按普通错误重试...');
    }
    if (!responseHasError(resp.body)) {
      console.log(resp.body);
      return;
    }
    attempt++;
    if (attempt < MAX_ATTEMPTS) {
      await sleep(3000);
    }
  }

  // 重试耗尽：最后一次响应的 HTTP 码与 body 是排查关键，必须打 stderr（同步、必被采集）。
  // 不用 process.exit()——它会截断未刷新的异步 stdout，导致诊断日志丢失。
  if (lastStatus !== null) {
    console.error(
      `[最后一次响应] HTTP ${lastStatus}, body: ${lastBody ? lastBody : '(empty)'}`
    );
  }
  if (lastNetworkError) {
    console.error(`网络错误重试耗尽: ${lastNetworkError.message}`);
  }
  process.exitCode = 1;
})().catch((e) => {
  console.error(`请求失败: ${e.message}`);
  process.exitCode = 1;
});
