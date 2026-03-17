"""
deep.network.protocol
~~~~~~~~~~~~~~~~~~~~~~~~~
DeepBridge Wire Protocol v1 based on PKT-LINE framing.

Each packet is prefixed by a 4-byte hex length (including the 4 bytes).
"0000" is a flush-pkt (special signal).
"""

from __future__ import annotations

import io
from typing import BinaryIO, Optional


FLUSH_PKT = b"0000"

# Side-band channels (v2)
BAND_DATA = 1
BAND_PROGRESS = 2
BAND_ERROR = 3


def encode_pkt(data: bytes) -> bytes:
    """Encode internal data into a PKT-LINE frame.
    
    If data is empty, returns b"0000" (flush-pkt).
    Otherwise, returns hex_len + data.
    """
    if not data:
        return FLUSH_PKT
    
    # Deep format: 4 hex digits for total length (including length itself)
    # Max size 65520 (65535 - 15)
    total_len = len(data) + 4
    if total_len > 65535:
        raise ValueError("Packet too large for PKT-LINE")
    
    header = f"{total_len:04x}".encode("ascii")
    return header + data


def decode_pkt(stream: BinaryIO) -> Optional[bytes]:
    """Decode a single PKT-LINE frame from a binary stream.
    
    Returns:
        bytes: The payload (without 4-byte header).
        None: If the packet was a flush-pkt (0000).
        
    Raises:
        EOFError: If the stream ends unexpectedly.
        ValueError: If the packet header is malformed.
    """
    header = stream.read(4)
    if len(header) < 4:
        if not header:
            # Clean EOF before any data
            raise EOFError("Unexpected EOF while reading PKT-LINE header")
        raise EOFError(f"Truncated PKT-LINE header: {header!r}")
    
    if header == FLUSH_PKT:
        return None
    
    try:
        total_len = int(header.decode("ascii"), 16)
    except (ValueError, UnicodeDecodeError):
        raise ValueError(f"Malformed PKT-LINE header: {header!r}")
    
    if total_len == 0:
        return None # Alternative flush? Deep standard uses 0000
    
    if total_len < 4:
        raise ValueError(f"Invalid PKT-LINE length: {total_len}")
    
    payload_len = total_len - 4
    payload = stream.read(payload_len)
    if len(payload) != payload_len:
        raise EOFError("Unexpected EOF while reading PKT-LINE payload")
    
    return payload


class PktLineStream:
    """Helper to read/write packets to a binary stream."""
    
    def __init__(self, reader: BinaryIO, writer: Optional[BinaryIO] = None):
        self.reader = reader
        self.writer = writer or reader

    def write(self, data: bytes):
        self.writer.write(encode_pkt(data))
        self.writer.flush()

    def flush(self):
        self.writer.write(FLUSH_PKT)
        self.writer.flush()

    def read_pkt(self) -> Optional[bytes]:
        return decode_pkt(self.reader)

    def read_until_flush(self) -> list[bytes]:
        """Read packets until a flush-pkt is encountered."""
        packets = []
        while True:
            pkt = self.read_pkt()
            if pkt is None:
                break
            packets.append(pkt)
        return packets


class AsyncPktLineStream:
    """Async helper to read/write packets to an asyncio Stream."""
    
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def write(self, data: bytes):
        self.writer.write(encode_pkt(data))
        await self.writer.drain()

    async def flush(self):
        self.writer.write(FLUSH_PKT)
        await self.writer.drain()

    async def read_pkt(self, timeout: float = 30.0) -> Optional[bytes]:
        import asyncio
        header = await asyncio.wait_for(self.reader.readexactly(4), timeout=timeout)
        if header == FLUSH_PKT:
            return None
        
        try:
            total_len = int(header.decode("ascii"), 16)
        except (ValueError, UnicodeDecodeError):
            raise ValueError(f"Malformed PKT-LINE header: {header!r}")
        
        if total_len == 0:
            return None
        if total_len < 4:
            raise ValueError(f"Invalid PKT-LINE length: {total_len}")
            
        payload = await asyncio.wait_for(self.reader.readexactly(total_len - 4), timeout=timeout)
        return payload

    async def read_until_flush(self) -> list[bytes]:
        packets = []
        while True:
            pkt = await self.read_pkt()
            if pkt is None:
                break
            packets.append(pkt)
        return packets


class AsyncSidebandStream:
    """Multiplexed stream for side-band communication (v2).
    
    Format: [4-byte binary length][1-byte band][payload]
    """
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def write_band(self, band: int, data: bytes):
        """Write data to a specific band."""
        import struct
        # total_len = 4 (length) + 1 (band) + len(data)
        total_len = 5 + len(data)
        header = struct.pack(">I", total_len)
        self.writer.write(header + bytes([band]) + data)
        await self.writer.drain()

    async def send_progress(self, msg: str):
        await self.write_band(BAND_PROGRESS, msg.encode("utf-8"))

    async def send_error(self, msg: str):
        await self.write_band(BAND_ERROR, msg.encode("utf-8"))

    async def send_data(self, data: bytes):
        await self.write_band(BAND_DATA, data)

    async def read_frame(self, timeout: float = 30.0) -> Optional[tuple[int, bytes]]:
        """Read a single frame. Returns (band, payload)."""
        import asyncio
        import struct
        try:
            header = await asyncio.wait_for(self.reader.readexactly(4), timeout=timeout)
            total_len = struct.unpack(">I", header)[0]
            if total_len < 5:
                raise ValueError(f"Invalid side-band frame length: {total_len}")
            
            payload_with_band = await asyncio.wait_for(self.reader.readexactly(total_len - 4), timeout=timeout)
            band = payload_with_band[0]
            payload = payload_with_band[1:]
            return band, payload
        except (asyncio.IncompleteReadError, EOFError):
            return None


class SidebandStream:
    """Synchronous multiplexed stream for side-band communication (v2)."""
    def __init__(self, reader: BinaryIO, writer: Optional[BinaryIO] = None):
        self.reader = reader
        self.writer = writer or reader

    def write_band(self, band: int, data: bytes):
        import struct
        total_len = 5 + len(data)
        header = struct.pack(">I", total_len)
        self.writer.write(header + bytes([band]) + data)
        self.writer.flush()

    def send_data(self, data: bytes):
        self.write_band(BAND_DATA, data)

    def read_frame(self) -> Optional[tuple[int, bytes]]:
        import struct
        header = self.reader.read(4)
        if len(header) < 4:
            return None
        total_len = struct.unpack(">I", header)[0]
        if total_len < 5:
            raise ValueError(f"Invalid side-band frame length: {total_len}")
        
        payload_with_band = self.reader.read(total_len - 4)
        if len(payload_with_band) < (total_len - 4):
            return None
        
        band = payload_with_band[0]
        payload = payload_with_band[1:]
        return band, payload

