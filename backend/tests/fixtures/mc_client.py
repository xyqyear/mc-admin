"""
Minimal Minecraft client for testing purposes.

Connects to Minecraft 1.21.10 servers (protocol 773) in offline mode
to send and receive chat messages.
"""

import asyncio
import hashlib
import json
import logging
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 774  # Minecraft 1.21.11


# =============================================================================
# Data Type Encoding/Decoding
# =============================================================================


def write_varint(value: int) -> bytes:
    """Encode integer as VarInt (7 bits per byte, MSB is continuation flag)."""
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            byte |= 0x80
        result.append(byte)
        if value == 0:
            break
    return bytes(result)


def read_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode VarInt, returns (value, bytes_consumed)."""
    result = 0
    shift = 0
    for i in range(5):  # VarInt max 5 bytes
        if offset + i >= len(data):
            raise ValueError("VarInt data truncated")
        byte = data[offset + i]
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, i + 1
        shift += 7
    raise ValueError("VarInt too long")


async def read_varint_from_stream(reader: asyncio.StreamReader) -> int:
    """Read VarInt directly from stream."""
    result = 0
    shift = 0
    for _ in range(5):
        byte_data = await reader.readexactly(1)
        byte = byte_data[0]
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result
        shift += 7
    raise ValueError("VarInt too long")


def write_string(value: str) -> bytes:
    """Encode string as VarInt length + UTF-8 bytes."""
    encoded = value.encode("utf-8")
    return write_varint(len(encoded)) + encoded


def read_string(data: bytes, offset: int = 0) -> tuple[str, int]:
    """Decode string, returns (value, bytes_consumed)."""
    length, consumed = read_varint(data, offset)
    string_data = data[offset + consumed : offset + consumed + length]
    return string_data.decode("utf-8"), consumed + length


def write_uuid(uuid_str: str) -> bytes:
    """Encode UUID as 16 bytes."""
    uuid_hex = uuid_str.replace("-", "")
    return bytes.fromhex(uuid_hex)


def read_uuid(data: bytes, offset: int = 0) -> tuple[str, int]:
    """Decode UUID from 16 bytes."""
    uuid_bytes = data[offset : offset + 16]
    uuid_hex = uuid_bytes.hex()
    return (
        f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
        f"{uuid_hex[16:20]}-{uuid_hex[20:]}"
    ), 16


def write_long(value: int) -> bytes:
    """Encode 64-bit signed integer as big-endian bytes."""
    return struct.pack(">q", value)


def write_ushort(value: int) -> bytes:
    """Encode 16-bit unsigned integer as big-endian bytes."""
    return struct.pack(">H", value)


def generate_offline_uuid(username: str) -> str:
    """Generate offline-mode UUID from username (MD5-based, version 3)."""
    md5 = hashlib.md5(f"OfflinePlayer:{username}".encode()).digest()
    uuid_bytes = bytearray(md5)
    uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x30  # Version 3
    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80  # Variant
    uuid_hex = bytes(uuid_bytes).hex()
    return (
        f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
        f"{uuid_hex[16:20]}-{uuid_hex[20:]}"
    )


# =============================================================================
# Data Classes and Enums
# =============================================================================


@dataclass
class ChatMessage:
    """Chat message received from server."""

    timestamp: datetime
    sender: str
    message: str


class ConnectionState(Enum):
    """Minecraft protocol connection states."""

    HANDSHAKING = 0
    LOGIN = 1
    CONFIGURATION = 2
    PLAY = 3
    DISCONNECTED = 4


# =============================================================================
# Packet IDs
# =============================================================================


class LoginPacketId:
    """Login state packet IDs."""

    # Clientbound
    DISCONNECT = 0x00
    ENCRYPTION_REQUEST = 0x01
    LOGIN_SUCCESS = 0x02
    SET_COMPRESSION = 0x03

    # Serverbound
    LOGIN_START = 0x00
    LOGIN_ACKNOWLEDGED = 0x03


class ConfigPacketId:
    """Configuration state packet IDs."""

    # Clientbound
    DISCONNECT = 0x02
    FINISH_CONFIGURATION = 0x03
    KEEP_ALIVE = 0x04
    REGISTRY_DATA = 0x07
    SELECT_KNOWN_PACKS = 0x0E

    # Serverbound
    CLIENT_INFORMATION = 0x00
    FINISH_CONFIGURATION_ACK = 0x03
    KEEP_ALIVE_RESPONSE = 0x04
    SELECT_KNOWN_PACKS_RESPONSE = 0x07


class PlayPacketId:
    """Play state packet IDs."""

    # Clientbound
    DISCONNECT = 0x20
    KEEP_ALIVE = 0x2B
    PLAYER_CHAT = 0x3F
    SYSTEM_CHAT = 0x77

    # Serverbound
    CHAT = 0x08
    KEEP_ALIVE_RESPONSE = 0x1B


# =============================================================================
# MinecraftClient
# =============================================================================


class MinecraftClient:
    """Minimal Minecraft client for testing chat functionality."""

    def __init__(
        self,
        username: str,
        on_chat: Optional[Callable[[ChatMessage], None]] = None,
    ):
        self._username = username
        self._on_chat = on_chat
        self._uuid = generate_offline_uuid(username)

        # Connection state
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._state = ConnectionState.DISCONNECTED
        self._connected_event = asyncio.Event()

        # Compression
        self._compression_threshold = -1  # -1 means disabled

        # Background tasks
        self._read_task: Optional[asyncio.Task] = None

    async def connect(self, host: str, port: int) -> None:
        """Connect to server and start login sequence."""
        logger.debug(f"Connecting to {host}:{port} as {self._username}")

        # Open TCP connection
        self._reader, self._writer = await asyncio.open_connection(host, port)
        self._state = ConnectionState.HANDSHAKING

        # Send Handshake packet
        await self._send_handshake(host, port)
        self._state = ConnectionState.LOGIN

        # Send Login Start packet
        await self._send_login_start()

        # Start packet reading loop
        self._read_task = asyncio.create_task(self._read_loop())

    async def wait_until_connected(self) -> None:
        """Wait until fully connected (in PLAY state)."""
        await self._connected_event.wait()

    async def send_chat(self, message: str) -> None:
        """Send a chat message to the server."""
        if self._state != ConnectionState.PLAY:
            raise RuntimeError("Not connected to server")

        # Build chat packet data for 1.21.5+ (protocol 770+)
        data = write_string(message)
        data += write_long(int(datetime.now().timestamp() * 1000))  # timestamp
        data += write_long(0)  # salt
        data += bytes([0])  # has signature (false)
        data += write_varint(0)  # message count (lastSeen offset)
        data += bytes([0, 0, 0])  # acknowledged bitset (20 bits = 3 bytes)
        data += bytes([0])  # checksum byte (required for 1.21.5+)

        await self._send_packet(PlayPacketId.CHAT, data)
        logger.debug(f"Sent chat message: {message}")

    async def disconnect(self) -> None:
        """Gracefully disconnect from server."""
        logger.debug("Disconnecting from server")
        self._state = ConnectionState.DISCONNECTED
        self._connected_event.clear()

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    # -------------------------------------------------------------------------
    # Packet Sending
    # -------------------------------------------------------------------------

    async def _send_packet(self, packet_id: int, data: bytes = b"") -> None:
        """Send a packet, handling compression if enabled."""
        if not self._writer:
            raise RuntimeError("Not connected")

        packet_data = write_varint(packet_id) + data

        if self._compression_threshold >= 0:
            if len(packet_data) >= self._compression_threshold:
                # Compress
                uncompressed_length = len(packet_data)
                compressed = zlib.compress(packet_data)
                packet_data = write_varint(uncompressed_length) + compressed
            else:
                # Don't compress, but include data length = 0
                packet_data = write_varint(0) + packet_data

        # Send with length prefix
        self._writer.write(write_varint(len(packet_data)) + packet_data)
        await self._writer.drain()

    async def _send_handshake(self, host: str, port: int) -> None:
        """Send Handshake packet."""
        data = write_varint(PROTOCOL_VERSION)
        data += write_string(host)
        data += write_ushort(port)
        data += write_varint(2)  # Next state: Login

        await self._send_packet(0x00, data)
        logger.debug("Sent Handshake packet")

    async def _send_login_start(self) -> None:
        """Send Login Start packet."""
        data = write_string(self._username)
        data += write_uuid(self._uuid)

        await self._send_packet(LoginPacketId.LOGIN_START, data)
        logger.debug(f"Sent Login Start packet for {self._username}")

    async def _send_login_acknowledged(self) -> None:
        """Send Login Acknowledged packet."""
        await self._send_packet(LoginPacketId.LOGIN_ACKNOWLEDGED)
        logger.debug("Sent Login Acknowledged packet")

    async def _send_client_information(self) -> None:
        """Send Client Information packet."""
        data = write_string("en_US")  # locale
        data += bytes([8])  # view distance
        data += write_varint(0)  # chat mode (enabled)
        data += bytes([1])  # chat colors
        data += bytes([0x7F])  # displayed skin parts (all)
        data += write_varint(1)  # main hand (right)
        data += bytes([0])  # enable text filtering
        data += bytes([1])  # allow server listings
        data += write_varint(0)  # particle status (all)

        await self._send_packet(ConfigPacketId.CLIENT_INFORMATION, data)
        logger.debug("Sent Client Information packet")

    async def _send_select_known_packs(self) -> None:
        """Send Select Known Packs response (empty)."""
        data = write_varint(0)  # No known packs
        await self._send_packet(ConfigPacketId.SELECT_KNOWN_PACKS_RESPONSE, data)
        logger.debug("Sent Select Known Packs response")

    async def _send_finish_configuration_ack(self) -> None:
        """Send Acknowledge Finish Configuration packet."""
        await self._send_packet(ConfigPacketId.FINISH_CONFIGURATION_ACK)
        logger.debug("Sent Finish Configuration Acknowledged packet")

    # -------------------------------------------------------------------------
    # Packet Reading
    # -------------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Main packet reading loop."""
        try:
            while self._state != ConnectionState.DISCONNECTED:
                packet_id, data = await self._read_packet()
                await self._handle_packet(packet_id, data)
        except asyncio.CancelledError:
            pass
        except asyncio.IncompleteReadError:
            logger.debug("Connection closed by server")
        except Exception as e:
            if self._state != ConnectionState.DISCONNECTED:
                logger.error(f"Error reading packet: {e}")
        finally:
            if self._state != ConnectionState.DISCONNECTED:
                self._state = ConnectionState.DISCONNECTED
                self._connected_event.clear()

    async def _read_packet(self) -> tuple[int, bytes]:
        """Read a packet, handling compression if enabled."""
        if not self._reader:
            raise RuntimeError("Not connected")

        # Read packet length
        length = await read_varint_from_stream(self._reader)

        # Read packet data
        data = await self._reader.readexactly(length)

        if self._compression_threshold >= 0:
            # Compression enabled
            data_length, consumed = read_varint(data)
            if data_length > 0:
                # Decompress
                data = zlib.decompress(data[consumed:])
            else:
                # Not compressed (below threshold)
                data = data[consumed:]

        # Parse packet ID
        packet_id, consumed = read_varint(data)
        return packet_id, data[consumed:]

    # -------------------------------------------------------------------------
    # Packet Handling
    # -------------------------------------------------------------------------

    async def _handle_packet(self, packet_id: int, data: bytes) -> None:
        """Route packet to appropriate handler based on state."""
        if self._state == ConnectionState.LOGIN:
            await self._handle_login_packet(packet_id, data)
        elif self._state == ConnectionState.CONFIGURATION:
            await self._handle_config_packet(packet_id, data)
        elif self._state == ConnectionState.PLAY:
            await self._handle_play_packet(packet_id, data)

    async def _handle_login_packet(self, packet_id: int, data: bytes) -> None:
        """Handle packets in LOGIN state."""
        if packet_id == LoginPacketId.DISCONNECT:
            reason, _ = read_string(data)
            logger.warning(f"Disconnected during login: {reason}")
            await self.disconnect()

        elif packet_id == LoginPacketId.SET_COMPRESSION:
            threshold, _ = read_varint(data)
            self._compression_threshold = threshold
            logger.debug(f"Compression enabled with threshold {threshold}")

        elif packet_id == LoginPacketId.LOGIN_SUCCESS:
            uuid, offset = read_uuid(data)
            username, _ = read_string(data, offset)
            logger.debug(f"Login success: {username} ({uuid})")

            # Send Login Acknowledged and transition to Configuration
            await self._send_login_acknowledged()
            self._state = ConnectionState.CONFIGURATION
            logger.debug("Transitioned to CONFIGURATION state")

    async def _handle_config_packet(self, packet_id: int, data: bytes) -> None:
        """Handle packets in CONFIGURATION state."""
        if packet_id == ConfigPacketId.DISCONNECT:
            reason, _ = read_string(data)
            logger.warning(f"Disconnected during configuration: {reason}")
            await self.disconnect()

        elif packet_id == ConfigPacketId.KEEP_ALIVE:
            keep_alive_id = struct.unpack(">q", data[:8])[0]
            await self._send_packet(
                ConfigPacketId.KEEP_ALIVE_RESPONSE, write_long(keep_alive_id)
            )
            logger.debug(f"Responded to config Keep Alive: {keep_alive_id}")

        elif packet_id == ConfigPacketId.SELECT_KNOWN_PACKS:
            await self._send_select_known_packs()

        elif packet_id == ConfigPacketId.FINISH_CONFIGURATION:
            # Send acknowledgment and transition to Play
            await self._send_finish_configuration_ack()
            self._state = ConnectionState.PLAY
            self._connected_event.set()
            logger.debug("Transitioned to PLAY state - fully connected")

    async def _handle_play_packet(self, packet_id: int, data: bytes) -> None:
        """Handle packets in PLAY state."""
        if packet_id == PlayPacketId.DISCONNECT:
            reason = self._parse_text_component(data)
            logger.warning(f"Disconnected: {reason}")
            await self.disconnect()

        elif packet_id == PlayPacketId.KEEP_ALIVE:
            keep_alive_id = struct.unpack(">q", data[:8])[0]
            await self._send_packet(
                PlayPacketId.KEEP_ALIVE_RESPONSE, write_long(keep_alive_id)
            )
            logger.debug(f"Responded to Keep Alive: {keep_alive_id}")

        elif packet_id == PlayPacketId.SYSTEM_CHAT:
            await self._handle_system_chat(data)

        elif packet_id == PlayPacketId.PLAYER_CHAT:
            await self._handle_player_chat(data)

    async def _handle_system_chat(self, data: bytes) -> None:
        """Handle System Chat packet."""
        content, offset = read_string(data)
        # overlay (boolean) at data[offset]

        message_text = self._extract_text_from_json(content)
        if message_text and self._on_chat:
            self._on_chat(
                ChatMessage(
                    timestamp=datetime.now(),
                    sender="SYSTEM",
                    message=message_text,
                )
            )

    async def _handle_player_chat(self, data: bytes) -> None:
        """Handle Player Chat packet for 1.21.5+ (protocol 770+)."""
        try:
            offset = 0

            # global index (VarInt) - new in 1.21.5
            _, consumed = read_varint(data, offset)
            offset += consumed

            # sender (UUID)
            sender_uuid, consumed = read_uuid(data, offset)
            offset += consumed

            # index (VarInt)
            _, consumed = read_varint(data, offset)
            offset += consumed

            # message_signature_present (Boolean)
            sig_present = data[offset]
            offset += 1

            if sig_present:
                # Skip signature (256 bytes)
                offset += 256

            # message (String) - the actual plain text message
            message, consumed = read_string(data, offset)
            offset += consumed

            # timestamp (Long)
            timestamp_ms = struct.unpack(">q", data[offset : offset + 8])[0]

            if self._on_chat:
                self._on_chat(
                    ChatMessage(
                        timestamp=datetime.fromtimestamp(timestamp_ms / 1000),
                        sender=sender_uuid,
                        message=message,
                    )
                )
        except Exception as e:
            logger.debug(f"Error parsing player chat: {e}")

    def _parse_text_component(self, data: bytes) -> str:
        """Parse text component from packet data."""
        try:
            content, _ = read_string(data)
            return self._extract_text_from_json(content)
        except Exception:
            return "<unknown>"

    def _extract_text_from_json(self, json_str: str) -> str:
        """Extract plain text from JSON text component."""
        try:
            obj = json.loads(json_str)
            return self._extract_text_recursive(obj)
        except json.JSONDecodeError:
            return json_str

    def _extract_text_recursive(self, obj) -> str:
        """Recursively extract text from text component object."""
        if isinstance(obj, str):
            return obj

        if isinstance(obj, dict):
            text = obj.get("text", "")
            if "extra" in obj:
                for extra in obj["extra"]:
                    text += self._extract_text_recursive(extra)
            if "translate" in obj:
                text += obj["translate"]
            return text

        if isinstance(obj, list):
            return "".join(self._extract_text_recursive(item) for item in obj)

        return str(obj)
