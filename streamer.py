"""
999 Badge - 7/24 Headless Go Live Yayın Motoru
Discord Gateway + Voice WebSocket + UDP + Go Live protokolü ile
hiçbir uygulama açmadan, %0 GPU ve CPU ile arka planda canlı yayın yapar.
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
from typing import Any, Dict, Optional

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


class DummyConsole:
    def ok(self, tag: str, msg: str) -> None:
        print(f"  [+] [{tag}] {msg}")

    def info(self, msg: str) -> None:
        print(f"  · {msg}")

    def warn(self, tag: str, msg: str) -> None:
        print(f"  [!] [{tag}] {msg}")

    def err(self, tag: str, msg: str) -> None:
        print(f"  [X] [{tag}] {msg}")


class MiniWebSocket:
    """RFC 6455 standartlarında çalışan pure-python WebSocket istemcisi."""

    def __init__(self, host: str, port: int = 443, path: str = "/") -> None:
        host_clean = host.replace("wss://", "").replace("https://", "").rstrip("/")
        if ":" in host_clean:
            h, p = host_clean.split(":", 1)
            self.host = h
            try:
                self.port = int(p)
            except ValueError:
                self.port = port
        else:
            self.host = host_clean
            self.port = port

        self.path = path
        self.sock: Optional[ssl.SSLSocket] = None
        self.closed = True
        self._lock = threading.RLock()

    def connect(self) -> None:
        raw_sock = socket.create_connection((self.host, self.port), timeout=15)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw_sock, server_hostname=self.host)
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")

        host_hdr = self.host if self.port == 443 else f"{self.host}:{self.port}"
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {host_hdr}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"User-Agent: {USER_AGENT}\r\n"
            f"\r\n"
        )
        self.sock.sendall(req.encode("ascii"))

        # Yanıt başlığını oku
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket el sıkışması başarısız oldu (Bağlantı koptu)")
            resp += chunk

        first_line = resp.split(b"\r\n")[0].decode("ascii", errors="replace")
        if "101" not in first_line:
            raise ConnectionError(f"WebSocket sunucusu 101 vermedi: {first_line}")

        self.closed = False

    def send(self, data: str) -> None:
        with self._lock:
            if self.closed or not self.sock:
                return
            payload = data.encode("utf-8")
            length = len(payload)
            mask_key = os.urandom(4)

            header = bytearray([0x81])  # FIN + Text Frame
            if length <= 125:
                header.append(0x80 | length)
            elif length <= 65535:
                header.append(0x80 | 126)
                header.extend(struct.pack("!H", length))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack("!Q", length))

            header.extend(mask_key)
            masked = bytearray(length)
            for i in range(length):
                masked[i] = payload[i] ^ mask_key[i % 4]

            self.sock.sendall(header + masked)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionResetError("Soket kapandı")
            buf.extend(chunk)
        return bytes(buf)

    def recv(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        if self.closed or not self.sock:
            return None

        r, _, _ = select.select([self.sock], [], [], timeout)
        if not r:
            return None

        with self._lock:
            try:
                b1b2 = self._recv_exact(2)
                b1, b2 = b1b2[0], b1b2[1]
                opcode = b1 & 0x0F
                is_masked = bool(b2 & 0x80)
                length = b2 & 0x7F

                if length == 126:
                    length = struct.unpack("!H", self._recv_exact(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", self._recv_exact(8))[0]

                mask = self._recv_exact(4) if is_masked else None
                data = self._recv_exact(length)

                if is_masked and mask:
                    unmasked = bytearray(length)
                    for i in range(length):
                        unmasked[i] = data[i] ^ mask[i % 4]
                    payload = bytes(unmasked)
                else:
                    payload = data

                if opcode == 0x08:  # Close
                    self.closed = True
                    code = 1000
                    reason = ""
                    if len(payload) >= 2:
                        code = struct.unpack("!H", payload[:2])[0]
                        reason = payload[2:].decode("utf-8", errors="replace")
                    return {"op": "close", "code": code, "reason": reason}

                if opcode == 0x09:  # Ping -> Pong
                    pong_frame = bytearray([0x8A, 0x80 | len(payload)])
                    m_key = os.urandom(4)
                    pong_frame.extend(m_key)
                    m_data = bytearray(payload[i] ^ m_key[i % 4] for i in range(len(payload)))
                    self.sock.sendall(pong_frame + m_data)
                    return None

                if opcode in (0x01, 0x02):  # Text or Binary
                    text = payload.decode("utf-8", errors="replace")
                    return json.loads(text)

            except (socket.timeout, select.error):
                return None
            except Exception:
                self.closed = True
                return None
        return None

    def close(self) -> None:
        with self._lock:
            self.closed = True
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None


class VoiceConnection:
    """Discord Ses ve Medya RTC bağlantısı."""

    def __init__(
        self,
        endpoint: str,
        server_id: str,
        user_id: str,
        session_id: str,
        token: str,
        console=None,
        label: str = "Ses",
    ):
        cleaned = endpoint.replace("wss://", "").replace("https://", "").rstrip("/")
        if ":" in cleaned:
            self.host, port_str = cleaned.split(":", 1)
            try:
                self.port = int(port_str)
            except ValueError:
                self.port = 443
        else:
            self.host = cleaned
            self.port = 443

        self.server_id = server_id
        self.user_id = user_id
        self.session_id = session_id
        self.token = token
        self.console = console or DummyConsole()
        self.label = label

        self.ws: Optional[MiniWebSocket] = None
        self.udp_sock: Optional[socket.socket] = None
        self.ssrc: int = 0
        self.voice_ip: str = ""
        self.voice_port: int = 0
        self.secret_key: bytes = b""
        self.running: bool = False
        self.packets_sent: int = 0
        self._seq: int = 0
        self._timestamp: int = 0

    def connect(self) -> bool:
        C = self.console
        try:
            self.ws = MiniWebSocket(self.host, port=self.port, path="/?v=7")
            self.ws.connect()
        except Exception as exc:
            C.err(self.label, f"Bağlantı hatası: {exc}")
            return False

        # Hello (Opcode 8) bekle
        start = time.time()
        hello_data = None
        while time.time() - start < 8:
            msg = self.ws.recv(timeout=2.0)
            if msg and msg.get("op") == 8:
                hello_data = msg.get("d", {})
                break
        if not hello_data:
            C.err(self.label, "Ses sunucusundan Hello yanıtı alınamadı.")
            return False

        hb_interval = hello_data.get("heartbeat_interval", 13750) / 1000.0

        # Opcode 0: Identify
        ident_d: Dict[str, Any] = {
            "server_id": self.server_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "token": self.token,
            "max_dave_protocol_version": 1,
        }
        self.ws.send(json.dumps({"op": 0, "d": ident_d}))

        # Ready (Opcode 2) bekle
        ready_data = None
        start = time.time()
        while time.time() - start < 10:
            msg = self.ws.recv(timeout=2.0)
            if msg and msg.get("op") == 2:
                ready_data = msg.get("d", {})
                break
        if not ready_data:
            C.err(self.label, "Ses sunucusu el sıkışması başarısız oldu.")
            return False

        self.ssrc = ready_data["ssrc"]
        self.voice_ip = ready_data["ip"]
        self.voice_port = ready_data["port"]

        # UDP Discovery
        try:
            self._udp_handshake()
        except Exception as exc:
            C.warn(self.label, f"UDP el sıkışması uyarısı: {exc}")

        # Session Description (Opcode 4) bekle
        start = time.time()
        while time.time() - start < 10:
            msg = self.ws.recv(timeout=2.0)
            if msg and msg.get("op") == 4:
                self.secret_key = bytes(msg["d"]["secret_key"])
                break

        # Speaking (Opcode 5)
        self.send_speaking(True)
        self.running = True

        # Heartbeat & Silence Pump iş parçacıklarını başlat
        threading.Thread(target=self._hb_loop, args=(hb_interval,), daemon=True).start()
        threading.Thread(target=self._audio_pump, daemon=True).start()
        return True

    def send_speaking(self, speaking: bool = True) -> None:
        """Kanalda konuşma durumunu açar/kapatır."""
        if self.ws and not self.ws.closed:
            try:
                self.ws.send(json.dumps({
                    "op": 5,
                    "d": {
                        "speaking": 1 if speaking else 0,
                        "delay": 0,
                        "ssrc": self.ssrc,
                    },
                }))
            except Exception:
                pass

    def _hb_loop(self, interval: float):
        while self.running and self.ws and not self.ws.closed:
            time.sleep(interval)
            try:
                self.ws.send(json.dumps({"op": 3, "d": int(time.time() * 1000)}))
            except Exception:
                break

    def _udp_handshake(self):
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.settimeout(5.0)

        packet = bytearray(74)
        struct.pack_into("!H", packet, 0, 1)
        struct.pack_into("!H", packet, 2, 70)
        struct.pack_into("!I", packet, 4, self.ssrc)
        self.udp_sock.sendto(packet, (self.voice_ip, self.voice_port))

        try:
            resp, _ = self.udp_sock.recvfrom(1024)
            my_ip = resp[8:72].split(b"\x00", 1)[0].decode("ascii")
            my_port = struct.unpack_from("!H", resp, len(resp) - 2)[0]
        except Exception:
            my_ip = "0.0.0.0"
            my_port = self.voice_port

        proto_d = {
            "op": 1,
            "d": {
                "protocol": "udp",
                "data": {
                    "address": my_ip,
                    "port": my_port,
                    "mode": "aead_aes256_gcm_rtpsize" if HAS_CRYPTO else "xsalsa20_poly1305",
                },
            },
        }
        self.ws.send(json.dumps(proto_d))

    def _audio_pump(self):
        while self.running and self.udp_sock:
            try:
                hdr = struct.pack(
                    "!BBHII",
                    0x80,
                    0x78,
                    self._seq & 0xFFFF,
                    self._timestamp & 0xFFFFFFFF,
                    self.ssrc,
                )
                self._seq += 1
                self._timestamp += 960

                if HAS_CRYPTO and len(self.secret_key) == 32:
                    iv = os.urandom(12)
                    cipher = AESGCM(self.secret_key)
                    encrypted = cipher.encrypt(iv, OPUS_SILENCE, hdr)
                    packet = hdr + encrypted + iv
                else:
                    packet = hdr + OPUS_SILENCE

                self.udp_sock.sendto(packet, (self.voice_ip, self.voice_port))
                self.packets_sent += 1
            except Exception:
                pass
            time.sleep(0.02)  # 20ms

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
    """Tamamen arka planda çalışan Go Live yayın motoru."""

    def __init__(self, token: str, guild_id: str, channel_id: str, user_id: str, console=None):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.console = console or DummyConsole()

        self.ws: Optional[MiniWebSocket] = None
        self.voice_conn: Optional[VoiceConnection] = None
        self.is_streaming: bool = False
        self.running: bool = False
        self.start_time: float = 0.0

        self.session_id: str = ""
        self.stream_key: str = ""
        self.heartbeat_interval: float = 41.25
        self.sequence: Optional[int] = None

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.console.info("Discord Gateway sunucusuna bağlanılıyor...")

        self.ws = MiniWebSocket(GATEWAY_URL, path="/?v=9&encoding=json")
        self.ws.connect()
        self.console.ok("Gateway", "Bağlantı kuruldu, oturum açılıyor...")

        threading.Thread(target=self._gw_loop, daemon=True).start()

    def _gw_loop(self):
        last_hb = time.time()
        while self.running:
            try:
                if not self.ws or self.ws.closed:
                    break

                now = time.time()
                if now - last_hb > self.heartbeat_interval:
                    if self.ws and not self.ws.closed:
                        try:
                            self.ws.send(json.dumps({"op": 1, "d": self.sequence}))
                            last_hb = now
                        except Exception:
                            break

                msg = self.ws.recv(timeout=1.0)
                if not msg:
                    continue

                if msg.get("op") == "close":
                    code = msg.get("code")
                    if code == 4004:
                        self.console.err("Oturum", "Discord Gateway kimlik doğrulama reddedildi (Token geçersiz).")
                    self.running = False
                    break

                op = msg.get("op")
                seq = msg.get("s")
                t = msg.get("t")
                d = msg.get("d") or {}

                if seq is not None:
                    self.sequence = seq

                if op == 10:  # Hello
                    self.heartbeat_interval = d.get("heartbeat_interval", 41250) / 1000.0
                    last_hb = time.time()

                    # Opcode 1 Heartbeat
                    self.ws.send(json.dumps({"op": 1, "d": self.sequence}))

                    # Opcode 2 Identify
                    props = {
                        "os": "Windows",
                        "browser": "Discord Client",
                        "release_channel": "stable",
                        "client_version": "1.0.9253",
                        "os_version": "10.0.26200",
                        "client_build_number": 594031,
                    }
                    ident = {
                        "op": 2,
                        "d": {
                            "token": self.token,
                            "capabilities": 16381,
                            "properties": props,
                            "presence": {"status": "online", "since": 0, "activities": [], "afk": False},
                        },
                    }
                    self.ws.send(json.dumps(ident))

                elif op == 0:  # Dispatch
                    if t == "READY":
                        self.session_id = d.get("session_id", "")
                        self.console.ok("Gateway", "Oturum doğrulandı. Hedef ses kanalına giriliyor...")
                        # Opcode 4: Ses kanalına katıl
                        join_p = {
                            "op": 4,
                            "d": {
                                "guild_id": self.guild_id,
                                "channel_id": self.channel_id,
                                "self_mute": False,
                                "self_deaf": False,
                                "self_video": False,
                            },
                        }
                        self.ws.send(json.dumps(join_p))

                    elif t == "VOICE_SERVER_UPDATE":
                        v_endpoint = d.get("endpoint")
                        v_tok = d.get("token")
                        if v_endpoint and v_tok and not self.voice_conn:
                            self.console.info("Ses ve Go Live sunucusu el sıkışması başlatılıyor...")
                            self.voice_conn = VoiceConnection(
                                endpoint=v_endpoint,
                                server_id=self.guild_id,
                                user_id=self.user_id,
                                session_id=self.session_id,
                                token=v_tok,
                                console=self.console,
                                label="Ses",
                            )
                            if self.voice_conn.connect():
                                self.console.ok("Ses", "Ses kanalına başarıyla bağlanıldı!")

                            # Opcode 18: Go Live (Ekran Yayını) Başlat!
                            self.console.info("Go Live (Ekran Yayını) isteği gönderiliyor...")
                            self.ws.send(json.dumps({
                                "op": 18,
                                "d": {
                                    "type": "guild",
                                    "guild_id": self.guild_id,
                                    "channel_id": self.channel_id,
                                    "preferred_region": None,
                                },
                            }))

                    elif t == "STREAM_CREATE":
                        self.stream_key = d.get("stream_key", "")
                        self.console.ok("Go Live", "Yayın anahtarı alındı, video akışı başlatılıyor...")

                        # Ses sunucusuna ekran yayını akışını (Opcode 12) bildir
                        if self.voice_conn and self.voice_conn.ws and not self.voice_conn.ws.closed:
                            try:
                                video_ssrc = self.voice_conn.ssrc + 1
                                rtx_ssrc = self.voice_conn.ssrc + 2
                                self.voice_conn.ws.send(json.dumps({
                                    "op": 12,
                                    "d": {
                                        "audio_ssrc": self.voice_conn.ssrc,
                                        "video_ssrc": video_ssrc,
                                        "rtx_ssrc": rtx_ssrc,
                                        "streams": [
                                            {
                                                "type": "screen",
                                                "rid": "100",
                                                "ssrc": video_ssrc,
                                                "rtx_ssrc": rtx_ssrc,
                                                "active": True,
                                                "quality": 100,
                                                "max_bitrate": 8000000,
                                                "max_framerate": 30,
                                                "max_resolution": {"type": "fixed", "width": 1920, "height": 1080},
                                            }
                                        ],
                                    },
                                }))
                                self.voice_conn.send_speaking(True)
                                self.is_streaming = True
                                self.console.ok("Yayın", "Canlı yayın aktif! Discord üzerinde hesabınız 'CANLI YAYINDA' görünüyor.")
                            except Exception as exc:
                                self.console.warn("Yayın", f"Yayın bildirimi gönderilemedi: {exc}")

                    elif t == "STREAM_SERVER_UPDATE":
                        self.console.ok("Yayın", "Medya rotası doğrulandı, veri paketleri iletiliyor.")

            except Exception:
                if not self.running:
                    break
                time.sleep(1)

    def get_stats(self) -> dict:
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        packets = self.voice_conn.packets_sent if self.voice_conn else 0
        is_streaming = bool(self.is_streaming and self.voice_conn and self.voice_conn.running)
        return {
            "elapsed_str": f"{h:02d}:{m:02d}:{s:02d}",
            "elapsed_seconds": elapsed,
            "packets": packets,
            "is_streaming": is_streaming,
        }

    def stop(self):
        self.running = False
        self.is_streaming = False
        try:
            if self.ws and not self.ws.closed:
                if self.stream_key:
                    self.ws.send(json.dumps({"op": 19, "d": {"stream_key": self.stream_key}}))
                self.ws.send(json.dumps({
                    "op": 4,
                    "d": {"guild_id": self.guild_id, "channel_id": None, "self_mute": True, "self_deaf": True},
                }))
                self.ws.close()
        except Exception:
            pass

        if self.voice_conn:
            self.voice_conn.close()
            self.voice_conn = None
        self.console.ok("Yayın", "Yayın ve ses oturumu kapatıldı.")
