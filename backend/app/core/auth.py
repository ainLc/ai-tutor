"""认证模块：密码加盐哈希 + 最小 JWT（HS256）。

全部用 Python 标准库实现，不引入额外依赖。
JWT 结构：base64url(header).base64url(payload).base64url(signature)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

# JWT 签名密钥（生产环境应从环境变量读取，这里给一个默认值并允许覆盖）
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ai-tutor-dev-secret-key-change-me")
TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 天


# ---------- 密码哈希 ----------

def hash_password(password: str) -> str:
    """用 PBKDF2-HMAC-SHA256 加盐哈希密码，返回 "salt$hash" 格式。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码是否匹配存储的哈希。"""
    try:
        salt, expected = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(dk.hex(), expected)
    except (ValueError, AttributeError):
        return False


# ---------- JWT ----------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user_id: str, username: str) -> str:
    """签发 JWT token。"""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + TOKEN_EXPIRE_SECONDS,
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    sig = hmac.new(SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def decode_token(token: str) -> dict | None:
    """校验并解析 JWT，返回 payload；无效或过期返回 None。"""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(SECRET_KEY.encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected_sig), sig_b64):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except (ValueError, json.JSONDecodeError, KeyError):
        return None
