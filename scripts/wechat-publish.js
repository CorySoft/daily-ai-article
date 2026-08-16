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

// ---- 可选的本机配置 ----
let config = {};
const configPath = opts.config || path.join(__dirname, 'client_config.json');
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
if (!body || !body.endsWith('}')) {
  console.error('请求体必须是 JSON 对象（--file <path> 或从 stdin 传入）');
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

// ---- 注入 credentials 字段（对象末尾追加）----
body = body.slice(0, -1) + `,"credentials":"${credPayload}"}`;

// ---- 发送 ----
const url = new URL(server + endpoint);
const isHttps = url.protocol === 'https:';
const transport = isHttps ? https : http;

const reqOpts = {
  hostname: url.hostname,
  path: url.pathname + url.search,
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-Shared-Secret': secret,
    'Content-Length': Buffer.byteLength(body),
  },
};
if (url.port) {
  reqOpts.port = Number(url.port);
}

const req = transport.request(reqOpts, (res) => {
  let out = '';
  res.on('data', (c) => { out += c; });
  res.on('end', () => { console.log(out); });
});
req.on('error', (e) => {
  console.error(`请求失败: ${e.message}`);
  process.exit(1);
});
req.write(body);
req.end();
