"""
999 Badge - Oyun Saati & Oyun Çeşitliliği Rozeti Motoru (Game Time & Game Variety)
Discord /api/v9/science telemetri sunucusuna doğrulanmış oyun oturumları iletir.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
GAMES_FILE = ROOT / "data" / "games.json"

ME_URL = "https://discord.com/api/v9/users/@me?with_analytics_token=true"
SCIENCE_URL = "https://discord.com/api/v9/science"
PROPERTIES_URL = "https://cordapi.dolfi.es/api/v2/properties/windows"
GAMES_CDN_URL = "https://raw.githubusercontent.com/Hikkywannafly/Discord-Verified-Games-List/main/detectable-games.json"

CLIENT_VERSION = "1.0.9253"
CLIENT_BUILD_NUMBER = 594031
NATIVE_BUILD_NUMBER = 88414
OS_VERSION = "10.0.26200"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9253 Chrome/148.0.7778.280 "
    "Electron/42.7.1 Safari/537.36"
)

BATCH_SIZE = 50
BATCH_DELAY = 1.0


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    exe: str


def _win_exe(game: dict) -> str:
    for entry in game.get("executables", []):
        if entry.get("os") == "win32" and entry.get("name"):
            return entry["name"]
    return "game.exe"


def _parse_games(raw: str) -> List[Game]:
    data = json.loads(raw)
    games: List[Game] = []
    seen = set()
    for entry in data:
        gid = str(entry.get("id", ""))
        if not gid.isdigit() or gid in seen:
            continue
        if not any(e.get("os") == "win32" and e.get("name") for e in entry.get("executables", [])):
            continue
        seen.add(gid)
        games.append(Game(gid, entry.get("name", "Unknown"), _win_exe(entry)))
    return games


def load_games() -> List[Game]:
    """games.json dosyasından oyunları yükler, yoksa alternatif GitHub kaynağından çeker."""
    if GAMES_FILE.exists():
        try:
            raw = GAMES_FILE.read_text(encoding="utf-8").strip()
            if raw:
                games = _parse_games(raw)
                if games:
                    return games
        except Exception:
            pass

    try:
        req = urllib.request.Request(GAMES_CDN_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
        GAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAMES_FILE.write_text(raw, encoding="utf-8")
        return _parse_games(raw)
    except Exception:
        return []


def _local_props() -> dict:
    return {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": CLIENT_VERSION,
        "os_version": OS_VERSION,
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "tr-TR",
        "has_client_mods": False,
        "browser_user_agent": USER_AGENT,
        "browser_version": "42.7.1",
        "os_sdk_version": "26200",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "native_build_number": NATIVE_BUILD_NUMBER,
        "client_event_source": None,
        "client_app_state": "focused",
    }


def build_super_props(launch_signature: str, heartbeat_session: str) -> str:
    try:
        req = urllib.request.Request(
            PROPERTIES_URL,
            method="POST",
            data=b"{}",
            headers={"content-type": "application/json", "user-agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            props = json.loads(response.read().decode("utf-8"))["properties"]
    except Exception:
        props = _local_props()
    props["client_launch_id"] = str(uuid.uuid4())
    props["launch_signature"] = launch_signature
    props["client_heartbeat_session_id"] = heartbeat_session
    raw = json.dumps(props, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def fetch_analytics_token(token: str, super_props: str) -> str:
    req = urllib.request.Request(ME_URL, headers={
        "authorization": token,
        "user-agent": USER_AGENT,
        "x-super-properties": super_props,
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Token reddedildi ({exc.code})") from exc
    at = data.get("analytics_token")
    if not at:
        raise RuntimeError("Discord analytics token dömedi.")
    return at


class ScienceClient:
    def __init__(self, token: str, cookie: str, super_props: str, analytics_token: str, launch_sig: str, heartbeat_session: str):
        self.token = token
        self.cookie = cookie
        self.super_props = super_props
        self.analytics_token = analytics_token
        self.launch_signature = launch_sig
        self.heartbeat_session = heartbeat_session
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def build_launch(self, game: Game) -> dict:
        now = int(time.time() * 1000)
        return {
            "type": "launch_game",
            "properties": {
                "client_track_timestamp": now,
                "client_heartbeat_session_id": self.heartbeat_session,
                "event_sequence_number": self._next_seq(),
                "game": game.name,
                "game_id": game.id,
                "verified": True,
                "elevated": False,
                "is_launcher": False,
                "game_platform": "desktop",
                "detection_method": "verified_game",
                "is_overlay_enabled": False,
                "is_overlay_game_enabled": True,
                "is_overlay_game_source": "OOP_DEFAULT_DATABASE",
                "fullscreen_type": "UNKNOWN",
                "hardware_display_count": 1,
                "overlay_method": "Disabled",
                "activity_status_enabled": True,
                "activity_status_shared_guilds": [],
                "current_user_status": "online",
                "game_detection_enabled": True,
                "executable_path": game.exe,
                "voice_channel_id": None,
                "voice_channel_type": None,
                "voice_channel_bitrate": None,
                "voice_channel_guild_id": None,
                "hidden_by_distributor": False,
                "game_metadata": None,
                "client_performance_cpu": None,
                "client_performance_memory": None,
                "cpu_core_count": None,
                "accessibility_features": 0,
                "rendered_locale": "tr-TR",
                "launch_signature": self.launch_signature,
                "client_rtc_state": None,
                "client_app_state": "focused",
                "client_send_timestamp": now,
            }
        }

    def build_heartbeat(self, game: Game, duration_ms: int, session_id: str, initial: bool, final: bool, ts: Optional[int] = None) -> dict:
        now = int(time.time() * 1000) if ts is None else ts
        return {
            "type": "running_game_heartbeat",
            "properties": {
                "client_track_timestamp": now,
                "client_heartbeat_session_id": self.heartbeat_session,
                "event_sequence_number": self._next_seq(),
                "game_id": game.id,
                "game_name": game.name,
                "game_metadata": None,
                "game_executable": game.exe,
                "game_detection_enabled": True,
                "initial_heartbeat": initial,
                "final_heartbeat": final,
                "game_session_id": session_id,
                "duration_tracked_ms": duration_ms,
                "rtc_connection_id": None,
                "media_session_id": None,
                "launch_signature": self.launch_signature,
                "client_app_state": "focused",
                "client_send_timestamp": now,
            }
        }

    def build_session(self, game: Game, duration_ms: int) -> list[dict]:
        sid = str(uuid.uuid4())
        now = int(time.time() * 1000)
        start = now - duration_ms
        if start < 0:
            start = now
        return [
            self.build_heartbeat(game, 0, sid, initial=True, final=False, ts=start),
            self.build_launch(game),
            self.build_heartbeat(game, duration_ms, sid, initial=False, final=True, ts=now),
        ]

    def post(self, events: Sequence[dict]) -> int:
        payload = {"token": self.analytics_token, "events": list(events)}
        body = json.dumps(payload).encode("utf-8")
        cookie_hdr = self.cookie.strip()
        if cookie_hdr and "cf_clearance=" not in cookie_hdr and "=" not in cookie_hdr:
            cookie_hdr = f"cf_clearance={cookie_hdr}"

        headers = {
            "accept": "*/*",
            "accept-language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": self.token,
            "content-type": "application/json",
            "cookie": cookie_hdr,
            "origin": "https://discord.com",
            "referer": "https://discord.com/channels/@me",
            "user-agent": USER_AGENT,
            "x-super-properties": self.super_props,
        }
        req = urllib.request.Request(SCIENCE_URL, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return 0


def _chunked(items: Sequence[Game], size: int) -> Iterator[Sequence[Game]]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def run_spoofer(
    token: str,
    cookie: str,
    games_to_claim: List[Game],
    hours_per_game_map: dict,  # game.id -> hours (float)
    console
) -> int:
    """Belirtilen oyunları ve süreleri Discord'a parça parça gönderir."""
    console.info("Discord telemetri oturumu hazırlanıyor...")
    hb = str(uuid.uuid4())
    sig = str(uuid.uuid4())
    super_props = build_super_props(sig, hb)

    try:
        analytics_token = fetch_analytics_token(token, super_props)
        console.ok("Telemetri", "Yetkilendirme anahtarı başarıyla alındı.")
    except Exception as e:
        console.err("Telemetri", f"Yetki alınamadı: {e}")
        return 0

    client = ScienceClient(token, cookie, super_props, analytics_token, sig, hb)
    total_games = len(games_to_claim)
    chunks = list(_chunked(games_to_claim, BATCH_SIZE))
    console.info(f"Toplam {total_games} oyun, {len(chunks)} paket halinde gönderilecek...")

    sent_ok = 0
    for idx, chunk in enumerate(chunks, 1):
        events = []
        for g in chunk:
            hours = hours_per_game_map.get(g.id, 1.0)
            duration_ms = int(hours * 3600 * 1000)
            events.extend(client.build_session(g, duration_ms))

        for attempt in range(3):
            status = client.post(events)
            if status == 204:
                sent_ok += len(chunk)
                console.ok(f"Paket {idx}/{len(chunks)}", f"{sent_ok}/{total_games} oyun işlendi (HTTP 204)")
                break
            elif status == 429:
                console.warn(f"Paket {idx}", "Hız sınırı (Rate Limit). 5 saniye bekleniyor...")
                time.sleep(5)
            elif status in (401, 403):
                console.err(f"Paket {idx}", f"Yetki reddedildi ({status}). Cookie güncel olmayabilir.")
                return sent_ok
            else:
                console.warn(f"Paket {idx}", f"HTTP {status} yanıtı. Tekrar deneniyor...")
                time.sleep(2)
        else:
            console.err(f"Paket {idx}", "3 denemeden sonra gönderilemedi.")

        time.sleep(BATCH_DELAY)

    return sent_ok
