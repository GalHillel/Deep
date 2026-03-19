"""
deep.network.pkt_line
~~~~~~~~~~~~~~~~~~~~~

PKT-line protocol implementation for Deep.

The pkt-line format is the wire protocol framing:
- Each packet has a 4-byte hex length prefix (including the 4 bytes itself)
- Payload follows immediately after the length
- Special packets:
  0000 = flush-pkt (end of section)
  0001 = delimiter-pkt (v2 protocol)
  0002 = response-end (v2 protocol)

Reference: Standard VCS wire protocol (pkt-line framing)
"""

from __future__ import annotations

import os
import sys
from typing import BinaryIO, Optional, List


FLUSH_PKT = b"0000"
DELIM_PKT = b"0001"
RESPONSE_END = b"0002"


def read_pkt_line(stream: BinaryIO) -> Optional[bytes]:
    """Read a single pkt-line frame from a binary stream.

    Returns:
        bytes: The payload (without the 4-byte header and without trailing LF).
        None: If flush-pkt (0000) was received.

    Raises:
        EOFError: If stream ends unexpectedly.
        ValueError: If the length is malformed.
    """
    header = stream.read(4)
    if len(header) < 4:
        if not header:
            raise EOFError("Connection closed")
        raise EOFError(f"Truncated pkt-line header: {header!r}")

    if header == FLUSH_PKT:
        if os.environ.get("DEEP_TRACE_PACKET"):
            print("[PKT] <<< 0000 (flush)", file=sys.stderr)
        return None

    if header == DELIM_PKT:
        if os.environ.get("DEEP_TRACE_PACKET"):
            print("[PKT] <<< 0001 (delim)", file=sys.stderr)
        return None

    if header == RESPONSE_END:
        if os.environ.get("DEEP_TRACE_PACKET"):
            print("[PKT] <<< 0002 (response-end)", file=sys.stderr)
        return None

    try:
        total_len = int(header.decode("ascii"), 16)
    except (ValueError, UnicodeDecodeError):
        raise ValueError(f"Malformed pkt-line header: {header!r}")

    if total_len == 0:
        return None

    if total_len < 4:
        raise ValueError(f"Invalid pkt-line length: {total_len}")

    payload_len = total_len - 4
    payload = stream.read(payload_len)
    if len(payload) != payload_len:
        raise EOFError(
            f"Truncated pkt-line payload: expected {payload_len}, "
            f"got {len(payload)}"
        )

    if os.environ.get("DEEP_TRACE_PACKET"):
        display = payload[:100]
        suffix = "..." if len(payload) > 100 else ""
        print(f"[PKT] <<< {display!r}{suffix}", file=sys.stderr)

    # Strip trailing newline if present
    if payload.endswith(b"\n"):
        payload = payload[:-1]

    return payload


def write_pkt_line(stream: BinaryIO, data: bytes) -> None:
    """Write a pkt-line frame to a binary stream.

    Args:
        data: Payload bytes (newline is NOT automatically appended).
    """
    if os.environ.get("DEEP_TRACE_PACKET"):
        display = data[:100]
        suffix = "..." if len(data) > 100 else ""
        print(f"[PKT] >>> {display!r}{suffix}", file=sys.stderr)

    # Add newline if not present
    if not data.endswith(b"\n"):
        data = data + b"\n"

    total_len = len(data) + 4
    if total_len > 65520:
        raise ValueError("pkt-line payload too large")

    header = f"{total_len:04x}".encode("ascii")
    stream.write(header + data)
    stream.flush()


def write_flush(stream: BinaryIO) -> None:
    """Write a flush-pkt (0000) to the stream."""
    if os.environ.get("DEEP_TRACE_PACKET"):
        print("[PKT] >>> 0000 (flush)", file=sys.stderr)
    stream.write(FLUSH_PKT)
    stream.flush()


def write_delim(stream: BinaryIO) -> None:
    """Write a delimiter-pkt (0001) to the stream."""
    stream.write(DELIM_PKT)
    stream.flush()


def read_pkt_lines(stream: BinaryIO) -> List[bytes]:
    """Read pkt-lines until a flush-pkt is received.

    Returns:
        List of payload byte strings (without headers/newlines).
    """
    lines = []
    while True:
        pkt = read_pkt_line(stream)
        if pkt is None:
            break
        lines.append(pkt)
    return lines


def read_sideband(stream: BinaryIO) -> Optional[bytes]:
    """Read a pkt-line with sideband-64k demuxing.

    Sideband channels:
        1 = pack data
        2 = progress messages
        3 = fatal error

    Returns:
        Pack data bytes (channel 1), or None on flush.

    Raises:
        RuntimeError: On server error (channel 3).
    """
    pkt = read_pkt_line(stream)
    if pkt is None:
        return None

    if not pkt:
        return b""

    channel = pkt[0]
    payload = pkt[1:]

    if channel == 1:
        return payload
    elif channel == 2:
        # Progress message
        msg = payload.decode("utf-8", errors="replace").strip()
        if os.environ.get("DEEP_DEBUG"):
            print(f"remote: {msg}", file=sys.stderr)
        return read_sideband(stream)  # Skip progress, read next
    elif channel == 3:
        error_msg = payload.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Server error: {error_msg}")
    else:
        # Unknown channel, treat as data
        return pkt
