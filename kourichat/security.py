"""Local secrets and WebUI administrator authentication."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


SECRET_ENV = "KOURICHAT_SECRET_KEY"
JWT_TTL_SECONDS = 8 * 60 * 60
# scrypt 参数：新记录用 OWASP 建议的 N=2^17；旧记录按记录里的 n 校验后渐进升级
SCRYPT_N = 2 ** 17
LEGACY_SCRYPT_N = 2 ** 14


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def secure_file(path: str | Path) -> None:
    """尽力把文件限制为当前用户可读写：POSIX chmod + Windows icacls。"""
    p = Path(path)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    if os.name == "nt":
        user = os.environ.get("USERNAME", "").strip()
        if not user:
            return
        try:
            import subprocess  # nosec B404 - 仅用于固定 icacls ACL 加固
            subprocess.run(  # nosec B603 B607 - 固定参数，无 shell，无用户输入拼接
                ["icacls", str(p), "/inheritance:r", "/grant:r", f"{user}:F"],
                capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            pass


class SecretStore:
    """Fernet-backed local secret store with an environment override."""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.key_path = self.root / ".secret-key"
        self._fernet: Fernet | None = None
        self._key: bytes | None = None

    def _load(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet
        raw = os.environ.get(SECRET_ENV, "").strip()
        if raw:
            key = raw.encode("ascii")
        elif self.key_path.exists():
            key = self.key_path.read_bytes().strip()
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            self.key_path.write_bytes(key + b"\n")
            try:
                secure_file(self.key_path)
            except OSError:
                pass
        try:
            self._fernet = Fernet(key)
            self._key = key
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"{SECRET_ENV} or {self.key_path} is not a valid Fernet key") from exc
        return self._fernet

    def encrypt(self, value: str) -> str:
        return self._load().encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._load().decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise ValueError("stored secret cannot be decrypted") from exc

    def put(self, name: str, value: str) -> str:
        if not name or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in name):
            raise ValueError("invalid secret name")
        values: dict[str, str] = {}
        if self.root.joinpath(".secrets.json").is_file():
            try:
                values = json.loads(self.root.joinpath(".secrets.json").read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError):
                values = {}
        values[name] = self.encrypt(value)
        path = self.root / ".secrets.json"
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(values, separators=(",", ":")) + "\n", encoding="utf-8")
        try:
            secure_file(tmp)
        except OSError:
            pass
        tmp.replace(path)
        return f"@secret:{name}"

    def get(self, name: str) -> str:
        path = self.root / ".secrets.json"
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            return self.decrypt(str(values[name]))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"secret {name!r} is unavailable") from exc

    def delete(self, name: str) -> None:
        path = self.root / ".secrets.json"
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return
        if name not in values:
            return
        del values[name]
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(values, separators=(",", ":")) + "\n", encoding="utf-8")
        try:
            secure_file(tmp)
        except OSError:
            pass
        tmp.replace(path)

    def signing_key(self) -> bytes:
        self._load()
        if self._key is None:
            raise RuntimeError("secret key not loaded")
        return hashlib.sha256(self._key + b"kourichat-jwt").digest()


class AdminAuth:
    """Password verifier and compact HS256 JWT issuer for the local WebUI."""

    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.path = self.root / ".webui-admin.json"
        self.revoked_path = self.root / ".revoked-tokens.json"
        self.secrets = SecretStore(self.root)
        self._revoked: dict[str, int] = self._load_revoked()

    @property
    def initialized(self) -> bool:
        return self.path.is_file()

    def setup(self, username: str, password: str) -> None:
        username = username.strip()
        if not 1 <= len(username) <= 64:
            raise ValueError("管理员账号长度必须为 1-64 个字符")
        if len(password) < 12 or len(password) > 256:
            raise ValueError("管理员密码长度必须为 12-256 个字符")
        if self.initialized:
            raise ValueError("管理员账号已初始化")
        salt = secrets.token_bytes(16)
        record = {
            "username": username,
            "salt": _b64(salt),
            "password_hash": _b64(self._hash(password, salt)),
            "kdf": "scrypt",
            "n": SCRYPT_N,
            "created_at": int(time.time()),
        }
        self._write_json(record, create_only=True)

    @staticmethod
    def _hash(password: str, salt: bytes, n: int = SCRYPT_N) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=8, p=1, dklen=32,
            maxmem=256 * 1024 * 1024)

    def verify(self, username: str, password: str) -> bool:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            salt = _unb64(str(record["salt"]))
            expected = _unb64(str(record["password_hash"]))
            n = int(record.get("n", LEGACY_SCRYPT_N))
            actual = self._hash(password, salt, n)
            ok = (hmac.compare_digest(str(record["username"]), username)
                  and hmac.compare_digest(actual, expected))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if ok and n < SCRYPT_N:
            try:
                new_salt = secrets.token_bytes(16)
                record.update({
                    "salt": _b64(new_salt),
                    "password_hash": _b64(self._hash(password, new_salt)),
                    "kdf": "scrypt",
                    "n": SCRYPT_N,
                })
                self._write_json(record)
            except OSError:
                pass
        return ok

    def issue(self, username: str) -> str:
        now = int(time.time())
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"sub": username, "iat": now, "exp": now + JWT_TTL_SECONDS}
        head = _b64(json.dumps(header, separators=(",", ":")).encode())
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        signing = f"{head}.{body}".encode("ascii")
        sig = hmac.new(self.secrets.signing_key(), signing, hashlib.sha256).digest()
        return f"{head}.{body}.{_b64(sig)}"

    def revoke(self, token: str) -> None:
        """吊销 token 并持久化（进程重启后仍有效，直到 exp 过期）。"""
        if not token:
            return
        exp = self._token_exp(token) or int(time.time()) + JWT_TTL_SECONDS
        self._revoked[token] = exp
        self._save_revoked()

    def is_revoked(self, token: str) -> bool:
        exp = self._revoked.get(token)
        if exp is None:
            return False
        if exp <= int(time.time()):
            self._revoked.pop(token, None)
            return False
        return True

    def _token_exp(self, token: str) -> int:
        try:
            payload = json.loads(_unb64(token.split(".")[1]))
            return int(payload.get("exp", 0))
        except (IndexError, ValueError, TypeError, binascii.Error, json.JSONDecodeError):
            return 0

    def _load_revoked(self) -> dict[str, int]:
        try:
            raw = json.loads(self.revoked_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        now = int(time.time())
        out: dict[str, int] = {}
        for key, value in (raw.items() if isinstance(raw, dict) else []):
            try:
                exp = int(value)
            except (TypeError, ValueError):
                continue
            if exp > now:
                out[str(key)] = exp
        return out

    def _save_revoked(self) -> None:
        now = int(time.time())
        self._revoked = {t: e for t, e in self._revoked.items() if e > now}
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.revoked_path.with_suffix(self.revoked_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._revoked, separators=(",", ":")),
                       encoding="utf-8")
        try:
            secure_file(tmp)
        except OSError:
            pass
        tmp.replace(self.revoked_path)

    def verify_token(self, token: str) -> str | None:
        if self.is_revoked(token):
            return None
        try:
            head, body, signature = token.split(".")
            signing = f"{head}.{body}".encode("ascii")
            expected = hmac.new(self.secrets.signing_key(), signing, hashlib.sha256).digest()
            if not hmac.compare_digest(_unb64(signature), expected):
                return None
            header = json.loads(_unb64(head))
            payload = json.loads(_unb64(body))
            if header.get("alg") != "HS256" or header.get("typ") != "JWT":
                return None
            if int(payload.get("exp", 0)) <= int(time.time()):
                return None
            subject = str(payload.get("sub") or "")
            return subject or None
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, binascii.Error):
            return None

    def _write_json(self, value: dict[str, Any], *, create_only: bool = False) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if create_only:
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise ValueError("管理员账号已初始化") from exc
            try:
                os.write(fd, content)
            finally:
                os.close(fd)
            secure_file(self.path)
            return
        tmp = self.path.with_suffix(self.path.suffix + f".{secrets.token_hex(8)}.tmp")
        tmp.write_bytes(content)
        try:
            secure_file(tmp)
        except OSError:
            pass
        tmp.replace(self.path)
