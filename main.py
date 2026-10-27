"""
✦ 999 BADGE ✦
Discord Profil Rozet Yöneticisi & Otomatik Kasma Aracı
Geliştirici: 999 Topluluğu (discord.gg/999)
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import sys
import time
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import browser_auth
import guild_gate
import spoofer
import streamer

# Terminal UTF-8 desteği
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "ayarlar.json"
OLD_STATE_FILE = ROOT.parent / "discord-badge-spoofer-6c95d9" / "science_state.json"

DEFAULT_GUILD_ID = "1318438089001144340"
DEFAULT_VOICE_CHANNEL_ID = "1509203606887202830"


class Console:
    """Türkçe ve renkli konsol arayüzü yöneticisi."""

    RED = "\x1b[91m"
    GREEN = "\x1b[92m"
    YELLOW = "\x1b[93m"
    CYAN = "\x1b[96m"
    MAGENTA = "\x1b[95m"
    WHITE = "\x1b[97m"
    GREY = "\x1b[90m"
    BOLD = "\x1b[1m"
    RESET = "\x1b[0m"
    RULE = "─" * 58

    def __init__(self):
        if sys.platform == "win32":
            self._enable_ansi()

    @staticmethod
    def _enable_ansi():
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)

    def _stamp(self) -> str:
        return f"{self.GREY}{time.strftime('%H:%M:%S')}{self.RESET}"

    def line(self, icon: str, title: str, msg: str, color: str):
        print(f"  {self._stamp()} {icon} {self.WHITE}{title}{self.RESET} {self.GREY}·{self.RESET} {color}{msg}{self.RESET}")

    def ok(self, title: str, msg: str):
        self.line(f"{self.GREEN}✓{self.RESET}", title, msg, self.GREEN)

    def info(self, msg: str):
        print(f"  {self._stamp()} {self.GREY}·{self.RESET} {self.WHITE}{msg}{self.RESET}")

    def warn(self, title: str, msg: str):
        self.line(f"{self.YELLOW}!{self.RESET}", title, msg, self.YELLOW)

    def err(self, title: str, msg: str):
        self.line(f"{self.RED}✗{self.RESET}", title, msg, self.RED)

    def rule(self):
        print(f"  {self.GREY}{self.RULE}{self.RESET}")

    def clear(self):
        print("\x1b[2J\x1b[3J\x1b[H", end="")

    def banner(self):
        self.clear()
        print(f"""
{self.CYAN}   ██████╗  ██████╗  ██████╗     ██████╗  █████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝ ██╔════╝ ██╔════╝     ██╔══██╗██╔══██╗██╔══██╗██╔════╝ ██╔════╝
  ███████╗ ███████╗ ███████╗     ██████╔╝███████║██║  ██║██║  ███╗█████╗  
  ╚════██║ ╚════██║ ╚════██║     ██╔══██╗██╔══██║██║  ██║██║   ██║██╔══╝  
  ███████║ ███████║ ███████║     ██████╔╝██║  ██║██████╔╝╚██████╔╝███████╗
  ╚══════╝ ╚══════╝ ╚══════╝     ╚═════╝ ╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚══════╝{self.RESET}
        {self.MAGENTA}✦ Discord Profil Rozet Yöneticisi & Otomatik Kasma Aracı ✦{self.RESET}
                 {self.GREY}Resmi Sunucu: {self.WHITE}discord.gg/999{self.RESET}
""")


@dataclass
class Settings:
    token: str = ""
    cookie: str = ""
    user_id: str = ""
    username: str = ""
    last_login: int = 0

    @classmethod
    def load(cls) -> "Settings":
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                return cls(**{k: data.get(k, "") for k in cls().__dict__.keys()})
            except Exception:
                pass

        # Eski oturum varsa otomatik taşı
        if OLD_STATE_FILE.exists():
            try:
                data = json.loads(OLD_STATE_FILE.read_text(encoding="utf-8"))
                token = data.get("token", "")
                cookie = data.get("cookie", "")
                if token:
                    s = cls(token=token, cookie=cookie)
                    s.save()
                    return s
            except Exception:
                pass
        return cls()

    def save(self):
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


class App:
    def __init__(self):
        self.console = Console()
        self.settings = Settings.load()
        self.games: List[spoofer.Game] = []
        self.active_streamer: Optional[streamer.HeadlessStreamEngine] = None

        # Güvenli kapanış kancası
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._handle_sigint)

    def _cleanup(self):
        if self.active_streamer and self.active_streamer.running:
            self.active_streamer.stop()

    def _handle_sigint(self, signum, frame):
        self._cleanup()
        print("\n\n  Çıkış yapıldı. İyi günler!\n")
        sys.exit(0)

    def start(self):
        self.console.banner()
        time.sleep(0.5)

        # 1. Adım: Token ve Cookie Sağlama
        if not self._ensure_auth():
            self.console.err("Giriş", "Hesap girişi yapılamadı, program kapatılıyor.")
            return

        # 2. Adım: Oyun Veritabanını Yükle
        self.console.rule()
        self.console.info("Doğrulanmış oyun veritabanı yükleniyor...")
        self.games = spoofer.load_games()
        if not self.games:
            self.console.err("Oyunlar", "Oyun veritabanı (games.json) yüklenemedi!")
            return
        self.console.ok("Oyunlar", f"{len(self.games)} adet doğrulanmış oyun hazır.")
        time.sleep(1)

        # 4. Adım: Ana Menü
        self.menu()

    def _ensure_auth(self) -> bool:
        C = self.console
        # Kayıtlı token geçerli mi?
        if self.settings.token:
            profile = browser_auth.validate_token(self.settings.token)
            if profile:
                self.settings.username = profile.get("username", "")
                self.settings.user_id = str(profile.get("id", ""))
                self.settings.save()
                C.ok("Giriş", f"Kayıtlı oturum yüklendi: {C.CYAN}{self.settings.username}{C.GREEN} ({self.settings.user_id})")
                return True
            else:
                C.warn("Oturum", "Kayıtlı tokenin süresi dolmuş veya geçersiz. Yenileniyor...")

        # Otomatik Tarayıcı / Masaüstü Taraması
        C.info("Bilgisayarınızdaki tarayıcılar ve Discord istemcisi taranıyor...")
        scanned = browser_auth.scan_local_tokens()

        if scanned:
            C.ok("Tarama", f"{len(scanned)} adet geçerli Discord hesabı tespit edildi:")
            print()
            for idx, (source, tok, prof) in enumerate(scanned, 1):
                uname = prof.get("username", "Bilinmeyen")
                uid = prof.get("id", "")
                print(f"    {C.CYAN}[{idx}]{C.WHITE} {source} {C.GREY}·{C.WHITE} Kullanıcı: {C.YELLOW}{uname}{C.WHITE} ({uid})")

            print(f"    {C.CYAN}[0]{C.WHITE} Manuel Token & Cookie Yapıştır")
            print()
            choice = input(f"  {C.CYAN}›{C.WHITE} Kullanmak istediğiniz hesabı seçin [1]: ").strip()
            if choice == "0":
                return self._prompt_manual_auth()
            try:
                selected_idx = int(choice) - 1 if choice else 0
                if 0 <= selected_idx < len(scanned):
                    src, tok, prof = scanned[selected_idx]
                    self.settings.token = tok
                    self.settings.username = prof.get("username", "")
                    self.settings.user_id = str(prof.get("id", ""))
                    self.settings.save()
                    C.ok("Seçildi", f"{self.settings.username} hesabı aktif edildi.")
                    self._ensure_cookie()
                    return True
            except ValueError:
                pass

        # Otomatik bulunamazsa manuel iste
        return self._prompt_manual_auth()

    def _prompt_manual_auth(self) -> bool:
        C = self.console
        C.rule()
        C.info("Manuel Discord Token Girişi")
        C.info("Tokeninizi Discord Web'de F12 > Network > authorization başlığından alabilirsiniz.")
        tok = input(f"  {C.CYAN}Token:{C.WHITE} ").strip().strip('"').strip("'")
        if not tok:
            return False

        profile = browser_auth.validate_token(tok)
        if not profile:
            C.err("Token", "Geçersiz Discord tokeni girdiniz!")
            return False

        self.settings.token = tok
        self.settings.username = profile.get("username", "")
        self.settings.user_id = str(profile.get("id", ""))
        self.settings.save()
        C.ok("Doğrulandı", f"Giriş başarılı: {self.settings.username}")
        self._ensure_cookie()
        return True

    def _ensure_cookie(self):
        C = self.console
        if self.settings.cookie:
            return
        C.rule()
        C.info("Discord cf_clearance Cookie Girişi (Oyun rozetleri için gereklidir)")
        C.info("F12 > Network sekmesinde /science isteğinin Request Headers > cookie başlığını yapıştırın.")
        cookie = input(f"  {C.CYAN}Cookie (veya boş bırakıp geçin):{C.WHITE} ").strip()
        if cookie:
            self.settings.cookie = cookie
            self.settings.save()
            C.ok("Cookie", "Kaydedildi.")

    def menu(self):
        C = self.console
        while True:
            self.console.banner()
            in_guild = guild_gate.is_user_in_guild(self.settings.token)
            guild_status = f"{C.GREEN}discord.gg/999 (Katılındı ✓){C.RESET}" if in_guild else f"{C.YELLOW}discord.gg/999 (Katılınmadı - Yalnızca Yayın İçin Gerekir){C.RESET}"
            print(f"  {C.WHITE}Giriş Yapılan Hesap:{C.RESET} {C.CYAN}{self.settings.username}{C.RESET} {C.GREY}({self.settings.user_id}){C.RESET}")
            print(f"  {C.WHITE}Yayın Sunucusu:{C.RESET}      {guild_status}")
            C.rule()
            print(f"  {C.CYAN}[1]{C.WHITE} 🎮 Oyun Çeşitliliği Rozeti {C.GREY}(Game Variety - İstediğiniz kadar oyun){C.RESET}")
            print(f"  {C.CYAN}[2]{C.WHITE} ⏱️ Oyun Saati Rozeti       {C.GREY}(Game Time - İstediğiniz kadar saat){C.RESET}")
            print(f"  {C.CYAN}[3]{C.WHITE} 🌟 Full Paket Rozet         {C.YELLOW}(999 Oyun & 9.999 Saat - Maksimum Seviye){C.RESET}")
            print(f"  {C.CYAN}[4]{C.WHITE} 📡 7/24 Headless Go Live    {C.MAGENTA}(discord.gg/999'da Arka Planda Yayın Rozeti Kasma){C.RESET}")
            print(f"  {C.CYAN}[5]{C.WHITE} 👤 Profil Bilgileri & Durum {C.GREY}(Kullanıcı ve Telemetri Bilgisi){C.RESET}")
            print(f"  {C.CYAN}[6]{C.WHITE} 🔄 Token / Cookie Değiştir  {C.GREY}(Başka bir hesaba geç){C.RESET}")
            print(f"  {C.CYAN}[0]{C.WHITE} 🚪 Çıkış{C.RESET}")
            C.rule()

            secim = input(f"  {C.CYAN}› Seçiminiz:{C.WHITE} ").strip()
            print()

            if secim == "1":
                self.action_game_variety()
            elif secim == "2":
                self.action_game_time()
            elif secim == "3":
                self.action_max_all()
            elif secim == "4":
                self.action_headless_stream()
            elif secim == "5":
                self.action_profile()
            elif secim == "6":
                self.settings.token = ""
                self.settings.cookie = ""
                self.settings.save()
                self._ensure_auth()
            elif secim in ("0", "q", "exit"):
                print(f"  {C.GREEN}999 Badge'i kullandığınız için teşekkürler! İyi günler.{C.RESET}\n")
                break
            else:
                C.warn("Menü", "Geçersiz seçenek seçtiniz!")
                time.sleep(1)

    def action_game_variety(self):
        C = self.console
        C.rule()
        C.info("Oyun Çeşitliliği Rozeti (Game Variety Badge)")
        C.info(f"Kullanılabilir toplam doğrulanmış oyun: {len(self.games)}")
        raw = input(f"  {C.CYAN}Kaç farklı oyun eklemek istersiniz? [100]:{C.WHITE} ").strip()
        count = int(raw) if raw.isdigit() else 100
        count = min(count, len(self.games))

        selected = self.games[:count]
        # Her oyuna 1 saat tanımla
        hours_map = {g.id: 1.0 for g in selected}

        C.info(f"{count} adet oyun Discord'a bildiriliyor...")
        sent = spoofer.run_spoofer(self.settings.token, self.settings.cookie, selected, hours_map, self.console)
        C.rule()
        C.ok("Tamamlandı", f"{sent}/{count} oyun başarıyla profilinize işlendi!")
        C.info("Rozetler Discord telemetri döngüsüne göre 24-48 saat içinde yansır.")
        input("\n  Ana menüye dönmek için Enter'a basın...")

    def action_game_time(self):
        C = self.console
        C.rule()
        C.info("Oyun Saati Rozeti (Game Time Badge)")
        raw_hours = input(f"  {C.CYAN}Toplam kaç saat oyun süresi eklemek istersiniz? [1000]:{C.WHITE} ").strip()
        try:
            total_hours = float(raw_hours) if raw_hours else 1000.0
        except ValueError:
            total_hours = 1000.0

        # En popüler 5 oyuna bu saati eşit dağıt
        game_count = min(5, len(self.games))
        selected = self.games[:game_count]
        hours_per_game = total_hours / game_count
        hours_map = {g.id: hours_per_game for g in selected}

        C.info(f"{game_count} ana oyuna toplam {total_hours:,.0f} saat basılıyor...")
        sent = spoofer.run_spoofer(self.settings.token, self.settings.cookie, selected, hours_map, self.console)
        C.rule()
        C.ok("Tamamlandı", f"Toplam {total_hours:,.0f} saat oyun süresi başarıyla işlendi!")
        C.info("Rozetler Discord telemetri döngüsüne göre 24-48 saat içinde yansır.")
        input("\n  Ana menüye dönmek için Enter'a basın...")

    def action_max_all(self):
        C = self.console
        C.rule()
        C.info("FULL PAKET: 999 Oyun & 9.999 Saat")
        C.info("Discord profilindeki hem Game Variety hem de Game Time rozetlerini maksimum seviyeye ulaştırır.")
        confirm = input(f"  {C.CYAN}İşlemi başlatmak istiyor musunuz? [E/H]:{C.WHITE} ").strip().lower()
        if confirm not in ("e", "evet", "y", "yes", ""):
            C.info("İşlem iptal edildi.")
            time.sleep(1)
            return

        target_count = min(999, len(self.games))
        selected = self.games[:target_count]

        # 1. oyuna 19 saat, diğer 998 oyuna 10 saat -> Toplam tam 9.999 saat!
        hours_map = {}
        for i, g in enumerate(selected):
            hours_map[g.id] = 19.0 if i == 0 else 10.0

        sent = spoofer.run_spoofer(self.settings.token, self.settings.cookie, selected, hours_map, self.console)
        C.rule()
        C.ok("Tebrikler!", f"{sent} oyun ve 9.999 saat başarıyla Discord sunucularına iletildi!")
        C.info("Rozetler Discord telemetri döngüsüne göre 24-48 saat içinde yansır.")
        input("\n  Ana menüye dönmek için Enter'a basın...")

    def action_headless_stream(self):
        C = self.console
        C.rule()
        C.info("7/24 Headless Go Live (Yayın Süresi Rozeti Kasma)")
        C.info("Discord.gg/999 sunucusunda arka planda %0 CPU/GPU harcayarak yayın yapar.")
        print(f"  {C.WHITE}Hedef Sunucu:{C.RESET} discord.gg/999 ({DEFAULT_GUILD_ID})")
        print(f"  {C.WHITE}Hedef Ses Kanalı:{C.RESET} 🏔️・Soul Society ({DEFAULT_VOICE_CHANNEL_ID})")
        C.rule()

        # Yayın yapabilmek için discord.gg/999 sunucusunda bulunulması gerekir
        if not guild_gate.ensure_guild_membership(self.settings.token, self.console):
            input("\n  Ana menüye dönmek için Enter'a basın...")
            return

        confirm = input(f"  {C.CYAN}Yayını başlatmak istiyor musunuz? [E/H]:{C.WHITE} ").strip().lower()
        if confirm not in ("e", "evet", "y", "yes", ""):
            return

        self.active_streamer = streamer.HeadlessStreamEngine(
            token=self.settings.token,
            guild_id=DEFAULT_GUILD_ID,
            channel_id=DEFAULT_VOICE_CHANNEL_ID,
            user_id=self.settings.user_id,
            console=self.console
        )

        try:
            self.active_streamer.start()
        except Exception as e:
            C.err("Yayın", f"Yayın başlatılamadı: {e}")
            input("\n  Devam etmek için Enter'a basın...")
            return

        print()
        C.ok("Canlı", "Headless Go Live yayını başlatıldı! Konsolu açık bıraktığınız sürece yayın devam eder.")
        C.info("Discord masaüstü uygulamasında ilgili ses kanalı açılıyor...")
        guild_gate.open_discord_channel(DEFAULT_GUILD_ID, DEFAULT_VOICE_CHANNEL_ID)
        C.info("Durdurmak için 'q' tuşlayıp Enter'a basabilir veya pencereyi kapatabilirsiniz.")
        print()

        try:
            while self.active_streamer.running:
                stats = self.active_streamer.get_stats()
                status_icon = f"{C.RED}🔴 YAYINDA{C.RESET}" if stats["is_streaming"] else f"{C.YELLOW}⏳ BAĞLANILIYOR{C.RESET}"
                print(
                    f"\r  {C.BOLD}[{status_icon}] Süre: {C.CYAN}{stats['elapsed_str']}{C.RESET} "
                    f"· Paket: {C.GREEN}{stats['packets']:,}{C.RESET} "
                    f"· Çıkmak için 'q' yazın: ",
                    end="",
                    flush=True
                )
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            print()
            if self.active_streamer:
                self.active_streamer.stop()
                self.active_streamer = None
        input("\n  Ana menüye dönmek için Enter'a basın...")

    def action_profile(self):
        C = self.console
        C.rule()
        C.info("Hesap Profil Bilgileri")
        profile = browser_auth.validate_token(self.settings.token)
        if profile:
            print(f"  {C.WHITE}Kullanıcı Adı:{C.RESET}   {C.CYAN}{profile.get('username')}{C.RESET}")
            print(f"  {C.WHITE}Kullanıcı ID:{C.RESET}    {C.CYAN}{profile.get('id')}{C.RESET}")
            print(f"  {C.WHITE}E-Posta:{C.RESET}         {C.CYAN}{profile.get('email', 'Gizli')}{C.RESET}")
            print(f"  {C.WHITE}Telefon:{C.RESET}         {C.CYAN}{profile.get('phone', 'Yok')}{C.RESET}")
            print(f"  {C.WHITE}2FA Doğrulama:{C.RESET}   {C.GREEN if profile.get('mfa_enabled') else C.RED}{profile.get('mfa_enabled')}{C.RESET}")
            in_guild = guild_gate.is_user_in_guild(self.settings.token)
            print(f"  {C.WHITE}999 Sunucusu:{C.RESET}    {C.GREEN if in_guild else C.RED}{'Katılındı ✓' if in_guild else 'Katılınmadı ✗'}{C.RESET}")
        else:
            C.err("Profil", "Profil bilgileri çekilemedi.")
        C.rule()
        input("\n  Ana menüye dönmek için Enter'a basın...")


def main():
    try:
        App().start()
    except KeyboardInterrupt:
        print("\n\n  Program sonlandırıldı. İyi günler!\n")


if __name__ == "__main__":
    main()
