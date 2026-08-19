#!/usr/bin/env node
// wechat-publish.js — 客户端发布脚本（跨平台，无需 PHP，仅需 Node.js）
// 依赖：Node.js 12+（内置 crypto / http / https，无任何 npm 包）
//
// 用法：
//   node client/wechat-publish.js [选项]
//
// 选项：
//   --config <path>    配置文件（默认 client/client_config.json，存在则加载）
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
// 请求体也可从 stdin 传入：echo '{"count":5}' | node client/wechat-publish.js --endpoint /draft/list
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

// 发送一次请求，返回 { statusCode, body }，网络错误 reject
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
    const reqOpts = {
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: httpMethod,
      headers,
    };
    if (url.port) {
      reqOpts.port = Number(url.port);
    }
    const req = transport.request(reqOpts, (res) => {
      let out = '';
      res.on('data', (c) => { out += c; });
      res.on('end', () => { resolve({ statusCode: res.statusCode, body: out }); });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
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

  const resp = await sendRequest(cookie);
  console.log(resp.body);
})().catch((e) => {
  console.error(`请求失败: ${e.message}`);
  process.exit(1);
});
