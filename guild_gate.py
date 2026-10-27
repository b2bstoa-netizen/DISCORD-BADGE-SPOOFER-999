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
INVITE_URL = "https://discord.gg/999"
DEFAULT_VOICE_CHANNEL_ID = "1509203606887202830"


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

    # İlk kontrol
    if is_user_in_guild(token, TARGET_GUILD_ID):
        ok("discord.gg/999 sunucu üyeliği doğrulandı.")
        return True

    warn("Bu işlemi kullanabilmek için 'discord.gg/999' sunucusunda bulunmanız gerekmektedir!")
    log(f"Tarayıcınızda davet bağlantısı açılıyor: {INVITE_URL}")
    webbrowser.open(INVITE_URL)

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
