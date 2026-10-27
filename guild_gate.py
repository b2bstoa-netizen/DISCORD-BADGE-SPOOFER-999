"""
999 Badge - Discord Sunucu Katılım Doğrulayıcısı (discord.gg/999)
Kullanıcının belirtilen sunucuda olup olmadığını kontrol eder, değilse yönlendirir.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Optional

TARGET_GUILD_ID = "1318438089001144340"
INVITE_CODE = "999"
INVITE_URL = "https://discord.gg/999"
DEFAULT_VOICE_CHANNEL_ID = "1509203606887202830"


def open_discord_invite():
    """Öncelikle Discord masaüstü uygulamasında daveti açar, uygulama yoksa web tarayıcısına yönlendirir."""
    # 1. Doğrudan Discord Masaüstü Uygulaması Protokolü
    try:
        import os
        if os.name == "nt":
            os.startfile(f"discord:///invite/{INVITE_CODE}")
            return
        else:
            webbrowser.open(f"discord:///invite/{INVITE_CODE}")
            return
    except Exception:
        pass

    # 2. Yedek: Web Tarayıcısı
    try:
        webbrowser.open(INVITE_URL)
    except Exception:
        pass


def open_discord_channel(guild_id: str = TARGET_GUILD_ID, channel_id: str = DEFAULT_VOICE_CHANNEL_ID):
    """Discord masaüstü uygulamasında ilgili ses kanalını doğrudan ekrana getirir."""
    try:
        import os
        target_uri = f"discord://-/channels/{guild_id}/{channel_id}"
        if os.name == "nt":
            os.startfile(target_uri)
        else:
            webbrowser.open(target_uri)
    except Exception:
        pass


def try_join_guild_api(token: str) -> bool:
    """Token ile Discord API üzerinden sunucuya otomatik katılmayı dener."""
    if not token:
        return False
    try:
        url = f"https://discord.com/api/v9/invites/{INVITE_CODE}"
        req = urllib.request.Request(url, data=b"{}", headers={
            "authorization": token.strip(),
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status in (200, 204):
                return True
    except Exception:
        pass
    return False


def is_user_in_guild(token: str, guild_id: str = TARGET_GUILD_ID) -> bool:
    """Kullanıcının verilen sunucuda olup olmadığını Discord API üzerinden kontrol eder."""
    if not token:
        return False
    url = "https://discord.com/api/v9/users/@me/guilds"
    req = urllib.request.Request(url, headers={
        "authorization": token.strip(),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                guilds = json.loads(resp.read().decode("utf-8"))
                return any(str(g.get("id")) == str(guild_id) for g in guilds)
    except Exception:
        pass
    return False


def ensure_guild_membership(token: str, console=None) -> bool:
    """
    Kullanıcının discord.gg/999 sunucusunda olduğundan emin olur.
    Sunucuda değilse tarayıcıda davet linkini açar ve onay bekler.
    """
    def log(msg: str):
        if console:
            console.info(msg)
        else:
            print(f"  · {msg}")

    def warn(msg: str):
        if console:
            console.warn("Sunucu", msg)
        else:
            print(f"  [!] {msg}")

    def ok(msg: str):
        if console:
            console.ok("Sunucu", msg)
        else:
            print(f"  [✓] {msg}")

    # 1. İlk kontrol
    if is_user_in_guild(token, TARGET_GUILD_ID):
        ok("discord.gg/999 sunucu üyeliği doğrulandı.")
        return True

    # 2. Otomatik API üzerinden katılmayı dene
    log("Sunucuya otomatik katılım deneniyor...")
    if try_join_guild_api(token):
        time.sleep(1)
        if is_user_in_guild(token, TARGET_GUILD_ID):
            ok("discord.gg/999 sunucusuna başarıyla otomatik katılım sağlandı!")
            return True

    # 3. Discord masaüstü uygulamasını aç
    warn("Yayın yapabilmek için 'discord.gg/999' sunucusunda bulunmanız gerekmektedir!")
    log("Discord masaüstü uygulamasında davet penceresi açılıyor...")
    open_discord_invite()

    while True:
        choice = input("\n  › Sunucuya katıldıktan sonra devam etmek için Enter'a basın (İptal için 'q'): ").strip().lower()
        if choice in ("q", "c", "iptal", "exit"):
            warn("Sunucu üyeliği doğrulanmadığı için işlem iptal edildi.")
            return False

        log("Sunucu üyeliği kontrol ediliyor...")
        time.sleep(1)
        if is_user_in_guild(token, TARGET_GUILD_ID):
            ok("Tebrikler! Sunucu üyeliğiniz başarıyla doğrulandı.")
            time.sleep(1)
            return True
        else:
            warn("Sunucuya henüz katılmadığınız tespit edildi. Lütfen daveti kabul edin.")
