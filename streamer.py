"""
999 Badge - 7/24 Headless Go Live Yayın Motoru (Streaming Badge Farmer)
Discord Gateway + Voice + Go Live WebRTC protokolünü kullanarak sıfır GPU/CPU ile
arka planda gerçek yayın süresi biriktirir (Streaming Badge).
"""

from __future__ import annotations

import base64
import json
import os
import random
import select
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.request
import uuid
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

OPUS_SILENCE = b"\xf8\xff\xfe"
GATEWAY_URL = "gateway.discord.gg"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9253 Chrome/148.0.7778.280 "
    "Electron/42.7.1 Safari/537.36"
)


class MiniWebSocket:
    """Python'ın standart socket ve ssl modülüyle çalışan hafif WebSocket istemcisi."""

    def __init__(self, host: str, path: str = "/", port: int = 443):
        self.host = host
        self.path = path
        self.port = port
        self.sock: Optional[ssl.SSLSocket] = None
        self._buf = bytearray()

    def connect(self, timeout: float = 10.0):
        ctx = ssl.create_default_context()
        raw = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock = ctx.wrap_socket(raw, server_hostname=self.host)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"User-Agent: {USER_AGENT}\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        res = self.sock.recv(4096)
        if b"101 Switching Protocols" not in res:
            raise RuntimeError(f"WebSocket el sıkışması başarısız: {res[:50]}")

    def send(self, data: str):
        payload = data.encode("utf-8")
        mask_key = os.urandom(4)
        masked = bytearray(len(payload))
        for i, b in enumerate(payload):
            masked[i] = b ^ mask_key[i % 4]

        frame = bytearray([0x81])  # text frame, fin=1
        length = len(payload)
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack("!Q", length))
        frame.extend(mask_key)
        frame.extend(masked)
        if self.sock:
            self.sock.sendall(frame)

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise ConnectionResetError("Soket kapandı.")
            self._buf.extend(chunk)
        res = bytes(self._buf[:n])
        del self._buf[:n]
        return res

    def recv(self, timeout: float = 5.0) -> Optional[str]:
        if not self.sock:
            return None
        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            return None
        try:
            head = self._recv_exact(2)
            length = head[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            payload = self._recv_exact(length)
            opcode = head[0] & 0x0F
            if opcode == 0x08:  # close frame
                return None
            if opcode == 0x01:  # text frame
                return payload.decode("utf-8", errors="replace")
        except Exception:
            return None
        return None

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None


class VoiceConnection:
    """Discord Ses/Stream WebSocket ve UDP akış yöneticisi."""

    def __init__(self, endpoint: str, token: str, session_id: str, guild_id: str, user_id: str, stream_key: Optional[str] = None):
        self.endpoint = endpoint.replace(":443", "")
        self.token = token
        self.session_id = session_id
        self.guild_id = guild_id
        self.user_id = user_id
        self.stream_key = stream_key
        self.ws: Optional[MiniWebSocket] = None
        self.udp_sock: Optional[socket.socket] = None
        self.ssrc: Optional[int] = None
        self.udp_ip: Optional[str] = None
        self.udp_port: Optional[int] = None
        self.secret_key: Optional[bytes] = None
        self.running = False
        self._seq = 0
        self._timestamp = 0
        self.packets_sent = 0

    def connect(self):
        self.ws = MiniWebSocket(self.endpoint, "/?v=7")
        self.ws.connect()
        # Opcode 0: Identify
        payload = {
            "op": 0,
            "d": {
                "server_id": self.guild_id,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "token": self.token,
                "video": bool(self.stream_key),
                "streams": [{"type": "screen", "rid": "100", "quality": 100}] if self.stream_key else [],
            }
        }
        self.ws.send(json.dumps(payload))

        ready = False
        start = time.time()
        while time.time() - start < 15:
            msg = self.ws.recv(timeout=2.0)
            if not msg:
                continue
            data = json.loads(msg)
            op = data.get("op")
            if op == 8:  # Hello
                hb_interval = data["d"]["heartbeat_interval"] / 1000.0
                threading.Thread(target=self._hb_loop, args=(hb_interval,), daemon=True).start()
            elif op == 2:  # Ready
                d = data["d"]
                self.ssrc = d["ssrc"]
                self.udp_ip = d["ip"]
                self.udp_port = d["port"]
                ready = True
                break

        if not ready:
            raise RuntimeError("Ses sunucusu el sıkışması başarısız oldu.")

        self._udp_handshake()

    def _hb_loop(self, interval: float):
        while self.running and self.ws:
            time.sleep(interval)
            try:
                self.ws.send(json.dumps({"op": 3, "d": int(time.time() * 1000)}))
            except Exception:
                break

    def _udp_handshake(self):
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # IP Discovery paketi (74 bayt)
        packet = bytearray(74)
        struct.pack_into("!H", packet, 0, 1)  # Request
        struct.pack_into("!H", packet, 2, 70)  # Length
        struct.pack_into("!I", packet, 4, self.ssrc)
        self.udp_sock.sendto(packet, (self.udp_ip, self.udp_port))

        resp, _ = self.udp_sock.recvfrom(1024)
        # Yanıt: IP ve Port ayrıştırma
        my_ip = resp[8:72].split(b"\x00", 1)[0].decode("ascii")
        my_port = struct.unpack_from("!H", resp, len(resp) - 2)[0]

        # Opcode 1: Select Protocol
        proto_payload = {
            "op": 1,
            "d": {
                "protocol": "udp",
                "data": {
                    "address": my_ip,
                    "port": my_port,
                    "mode": "aead_aes256_gcm_rtpsize" if HAS_CRYPTO else "xsalsa20_poly1305"
                }
            }
        }
        self.ws.send(json.dumps(proto_payload))

        # Session Description (Opcode 4) bekle
        start = time.time()
        while time.time() - start < 10:
            msg = self.ws.recv(timeout=2.0)
            if not msg:
                continue
            data = json.loads(msg)
            if data.get("op") == 4:
                self.secret_key = bytes(data["d"]["secret_key"])
                break

        # Speaking Opcode 5
        self.ws.send(json.dumps({"op": 5, "d": {"speaking": 1, "delay": 0, "ssrc": self.ssrc}}))
        self.running = True
        threading.Thread(target=self._pump_loop, daemon=True).start()

    def _pump_loop(self):
        """Her 20ms'de bir boş ses/görüntü paketi göndererek yayını aktif tutar."""
        while self.running and self.udp_sock and self.secret_key:
            try:
                # RTP Başlığı (12 bayt)
                header = struct.pack(
                    "!BBHII",
                    0x80,
                    0x78,
                    self._seq & 0xFFFF,
                    self._timestamp & 0xFFFFFFFF,
                    self.ssrc
                )
                self._seq += 1
                self._timestamp += 960

                if HAS_CRYPTO and len(self.secret_key) == 32:
                    iv = os.urandom(12)
                    cipher = AESGCM(self.secret_key)
                    encrypted = cipher.encrypt(iv, OPUS_SILENCE, header)
                    packet = header + encrypted + iv
                else:
                    packet = header + OPUS_SILENCE

                self.udp_sock.sendto(packet, (self.udp_ip, self.udp_port))
                self.packets_sent += 1
            except Exception:
                pass
            time.sleep(0.02)  # 20ms per frame

    def close(self):
        self.running = False
        try:
            if self.ws:
                self.ws.close()
            if self.udp_sock:
                self.udp_sock.close()
        except Exception:
            pass


class HeadlessStreamEngine:
    """Tam Gateway entegrasyonlu Go Live motoru."""

    def __init__(self, token: str, guild_id: str, channel_id: str, user_id: str, console):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.console = console
        self.gateway_ws: Optional[MiniWebSocket] = None
        self.voice_conn: Optional[VoiceConnection] = None
        self.stream_conn: Optional[VoiceConnection] = None
        self.session_id: Optional[str] = None
        self.stream_key: Optional[str] = None
        self.running = False
        self.start_time = 0.0

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.console.info("Discord Gateway sunucusuna bağlanılıyor...")

        self.gateway_ws = MiniWebSocket(GATEWAY_URL, "/?v=9&encoding=json")
        self.gateway_ws.connect()

        # Identify
        props = {
            "os": "Windows",
            "browser": "Discord Client",
            "device": "desktop"
        }
        ident = {
            "op": 2,
            "d": {
                "token": self.token,
                "capabilities": 16381,
                "properties": props,
                "presence": {"status": "online", "since": 0, "activities": [], "afk": False}
            }
        }
        self.gateway_ws.send(json.dumps(ident))

        # Event loop thread
        threading.Thread(target=self._gw_loop, daemon=True).start()

    def _gw_loop(self):
        while self.running and self.gateway_ws:
            msg = self.gateway_ws.recv(timeout=2.0)
            if not msg:
                continue
            data = json.loads(msg)
            op = data.get("op")
            t = data.get("t")
            d = data.get("d")

            if op == 10:  # Hello
                hb_interval = d["heartbeat_interval"] / 1000.0
                threading.Thread(target=self._gw_hb_loop, args=(hb_interval,), daemon=True).start()

            elif t == "READY":
                self.session_id = d["session_id"]
                self.console.ok("Gateway", "Oturum açıldı, ses kanalına bağlanılıyor...")
                # Opcode 4: Ses kanalına katıl
                join_payload = {
                    "op": 4,
                    "d": {
                        "guild_id": self.guild_id,
                        "channel_id": self.channel_id,
                        "self_mute": False,
                        "self_deaf": False,
                        "self_video": False
                    }
                }
                self.gateway_ws.send(json.dumps(join_payload))

            elif t == "VOICE_SERVER_UPDATE":
                endpoint = d.get("endpoint")
                v_token = d.get("token")
                if endpoint and v_token and not self.stream_key:
                    self.console.info("Ses sunucusu el sıkışması tamamlanıyor...")
                    try:
                        self.voice_conn = VoiceConnection(endpoint, v_token, self.session_id, self.guild_id, self.user_id)
                        self.voice_conn.connect()
                    except Exception as e:
                        self.console.warn("Ses", f"Hata: {e}")

                    # Opcode 18: Go Live (Stream Create) Başlat!
                    self.console.info("Go Live (Ekran Yayını) başlatılıyor...")
                    stream_payload = {
                        "op": 18,
                        "d": {
                            "type": "guild",
                            "guild_id": self.guild_id,
                            "channel_id": self.channel_id,
                            "preferred_region": None
                        }
                    }
                    self.gateway_ws.send(json.dumps(stream_payload))

            elif t == "STREAM_CREATE":
                self.stream_key = d.get("stream_key")
                self.console.ok("Go Live", f"Yayın anahtarı oluşturuldu: {self.stream_key}")

            elif t == "STREAM_SERVER_UPDATE":
                s_endpoint = d.get("endpoint")
                s_token = d.get("token")
                if s_endpoint and s_token and self.stream_key:
                    self.console.ok("Yayın", "Yayın sunucusu bağlandı, canlı akış başlatıldı! 🔴")
                    try:
                        self.stream_conn = VoiceConnection(s_endpoint, s_token, self.session_id, self.guild_id, self.user_id, self.stream_key)
                        self.stream_conn.connect()
                    except Exception as e:
                        self.console.warn("Yayın", f"Bağlantı uyarısı: {e}")

    def _gw_hb_loop(self, interval: float):
        while self.running and self.gateway_ws:
            time.sleep(interval)
            try:
                self.gateway_ws.send(json.dumps({"op": 1, "d": None}))
            except Exception:
                break

    def get_stats(self) -> dict:
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        packets = (self.voice_conn.packets_sent if self.voice_conn else 0) + (self.stream_conn.packets_sent if self.stream_conn else 0)
        return {
            "elapsed_str": f"{h:02d}:{m:02d}:{s:02d}",
            "elapsed_seconds": elapsed,
            "packets": packets,
            "is_streaming": bool(self.stream_conn and self.stream_conn.running),
        }

    def stop(self):
        """Kullanıcı konsolu kapattığında veya iptal ettiğinde yayını güvenle kapatır."""
        self.running = False
        try:
            if self.gateway_ws:
                # Opcode 19: Stream Delete
                if self.stream_key:
                    self.gateway_ws.send(json.dumps({"op": 19, "d": {"stream_key": self.stream_key}}))
                # Opcode 4: Leave Voice
                self.gateway_ws.send(json.dumps({
                    "op": 4,
                    "d": {"guild_id": self.guild_id, "channel_id": None, "self_mute": True, "self_deaf": True}
                }))
                self.gateway_ws.close()
        except Exception:
            pass

        if self.voice_conn:
            self.voice_conn.close()
        if self.stream_conn:
            self.stream_conn.close()
        self.console.ok("Yayın", "Yayın ve ses oturumu kapatıldı.")
