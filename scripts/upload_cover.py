# -*- coding: utf-8 -*-
"""Upload cover.png to WeChat via wechat-publisher, inject thumb_media_id into article.json."""
import json
import os
import re
import subprocess
import sys
import http.client
import http.cookiejar
from urllib.parse import urlparse, urlencode
from email.mime.multipart import MIMEMultipart

def encrypt_credentials(secret, appid, appsecret):
    """AES-256-CBC + HMAC-SHA256 encrypted credentials (matches wechat-publish.js)."""
    import hashlib, hmac as hmac_mod, os as _os, base64
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
    except ImportError:
        # fallback: subprocess to node
        return None
    key = hashlib.sha256(secret.encode()).digest()
    iv = _os.urandom(16)
    cred_json = json.dumps({"app_id": appid, "app_secret": appsecret})
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(cred_json.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    ct = base64.b64encode(enc.update(padded) + enc.finalize()).decode()
    mac = hmac_mod.new(key, (iv.hex() + ct).encode(), hashlib.sha256).hexdigest()
    return f"v1:{iv.hex()}:{mac}:{ct}"

def encrypt_credentials_fallback(secret, appid, appsecret):
    """Encrypt credentials using node (fallback when cryptography not installed)."""
    js = f"""
const crypto = require('crypto');
const secret = {json.dumps(secret)};
const appId = {json.dumps(appid)};
const appSecret = {json.dumps(appsecret)};
const keyHex = crypto.createHash('sha256').update(secret).digest('hex');
const iv = crypto.randomBytes(16);
const credJson = JSON.stringify({{ app_id: appId, app_secret: appSecret }});
const cipher = crypto.createCipheriv('aes-256-cbc', Buffer.from(keyHex, 'hex'), iv);
const ct = Buffer.concat([cipher.update(credJson, 'utf8'), cipher.final()]).toString('base64');
const mac = crypto.createHmac('sha256', keyHex).update(iv.toString('hex') + ct).digest('hex');
console.log(`v1:${{iv.toString('hex')}}:${{mac}}:${{ct}}`);
"""
    result = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else None

def unlock(password, hostname):
    """Unlock abeiyun debug domain, return cookie token string."""
    try:
        result = subprocess.run([
            "curl", "-s", "-m", "15", "-X", "POST",
            f"https://api.abeiyun.com/www/break.php?cmd=visit_sysdomain&password={password}",
            "-H", "Content-Type: application/x-www-form-urlencoded",
            "-H", f"Referer: http://{hostname}/",
            "-d", "x=1",
        ], capture_output=True, text=True, timeout=20)
        m = re.search(r"<errMsg>([^<]+)</errMsg>", result.stdout)
        return m.group(1).strip() if m else None
    except Exception as e:
        print(f"unlock failed: {e}")
        return None

def upload_cover(server, secret, appid, appsecret, password, cover_path):
    """Upload cover image via multipart/form-data, return media_id."""
    parsed = urlparse(server)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Unlock if abeiyun
    cookie_token = None
    if "abeiyun.cn" in hostname:
        cookie_token = unlock(password, hostname)
        if not cookie_token:
            print("unlock failed")
            return None

    # Encrypt credentials
    creds = encrypt_credentials(secret, appid, appsecret)
    if not creds:
        creds = encrypt_credentials_fallback(secret, appid, appsecret)
    if not creds:
        print("credential encryption failed")
        return None

    # Build multipart body
    boundary = "----DailyAI" + os.urandom(8).hex()
    with open(cover_path, "rb") as f:
        file_data = f.read()

    parts = []
    # credentials field
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"credentials\"\r\n\r\n{creds}".encode())
    # file field
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cover.png\"\r\nContent-Type: image/png\r\n\r\n".encode())
    parts.append(file_data)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"\r\n".join(parts)

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "X-Shared-Secret": secret,
    }
    if cookie_token:
        headers["Cookie"] = f"zhujiwusysdomain={cookie_token}"

    # Send request
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(hostname, port, timeout=30)
    else:
        conn = http.client.HTTPConnection(hostname, port, timeout=30)

    path = parsed.path or "/upload"
    qs = parsed.query or ""
    if qs:
        path += "?" + qs
    # Ensure upload endpoint
    if "/upload" not in path:
        path = "/upload"

    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode()
        print(f"upload status: {resp.status}, body: {data[:200]}")
        if resp.status == 200:
            result = json.loads(data)
            return result.get("media_id")
        # Check if locked (门禁)
        if resp.status in (301, 302, 403) or "门禁" in data or "sysdomain" in data.lower():
            print("got lock page, retrying unlock...")
            cookie_token = unlock(password, hostname)
            if cookie_token:
                headers["Cookie"] = f"zhujiwusysdomain={cookie_token}"
                conn2 = http.client.HTTPSConnection(hostname, port, timeout=30) if parsed.scheme == "https" else http.client.HTTPConnection(hostname, port, timeout=30)
                conn2.request("POST", path, body=body, headers=headers)
                resp2 = conn2.getresponse()
                data2 = resp2.read().decode()
                print(f"retry status: {resp2.status}, body: {data2[:200]}")
                if resp2.status == 200:
                    return json.loads(data2).get("media_id")
    except Exception as e:
        print(f"upload error: {e}")
    finally:
        conn.close()
    return None

def main():
    server = os.environ.get("WX_SERVER", "")
    secret = os.environ.get("WX_SHARED_SECRET", "")
    password = os.environ.get("WX_UNLOCK_PASSWORD", "")
    appid = os.environ.get("WX_APPID", "")
    appsecret = os.environ.get("WX_APPSECRET", "")
    cover_path = os.path.join("output", "cover.png")
    article_path = os.path.join("output", "article.json")

    if not os.path.exists(cover_path):
        print("no cover.png, skip")
        return

    media_id = upload_cover(server, secret, appid, appsecret, password, cover_path)
    if not media_id:
        print("upload failed, skip")
        return

    print(f"cover uploaded, media_id: {media_id}")

    if os.path.exists(article_path):
        with open(article_path) as f:
            d = json.load(f)
        d["articles"][0]["thumb_media_id"] = media_id
        with open(article_path, "w") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print("article.json updated with thumb_media_id")

if __name__ == "__main__":
    main()
