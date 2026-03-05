"""
tests.test_protocol
~~~~~~~~~~~~~~~~~~~
Tests for PKT-LINE framing in deep.network.protocol.
"""

from __future__ import annotations

import io
import pytest
from deep.network.protocol import encode_pkt, decode_pkt, FLUSH_PKT, PktLineStream


def test_encode_pkt():
    assert encode_pkt(b"hello") == b"0009hello"
    assert encode_pkt(b"") == b"0000"
    assert encode_pkt(b"a" * 10) == b"000ea" + b"a" * 9


def test_decode_pkt():
    # Regular packet
    stream = io.BytesIO(b"0009hello")
    assert decode_pkt(stream) == b"hello"
    
    # Flush packet
    stream = io.BytesIO(b"0000")
    assert decode_pkt(stream) is None
    
    # Multiple packets
    stream = io.BytesIO(b"0009hello0009world")
    assert decode_pkt(stream) == b"hello"
    assert decode_pkt(stream) == b"world"


def test_decode_pkt_errors():
    # Truncated header
    with pytest.raises(EOFError):
        decode_pkt(io.BytesIO(b"000"))
    
    # Truncated payload
    with pytest.raises(EOFError):
        decode_pkt(io.BytesIO(b"000aabc")) # header says 10, payload only 3 (abc)
    
    # Malformed header
    with pytest.raises(ValueError, match="Malformed PKT-LINE header"):
        decode_pkt(io.BytesIO(b"zzzz"))


def test_pkt_line_stream():
    buf = io.BytesIO()
    stream = PktLineStream(buf)
    
    stream.write(b"line 1")
    stream.write(b"line 2")
    stream.flush()
    
    buf.seek(0)
    assert stream.read_pkt() == b"line 1"
    assert stream.read_pkt() == b"line 2"
    assert stream.read_pkt() is None # Flush


def test_read_until_flush():
    raw = encode_pkt(b"p1") + encode_pkt(b"p2") + FLUSH_PKT + encode_pkt(b"p3")
    stream = PktLineStream(io.BytesIO(raw))
    
    packets = stream.read_until_flush()
    assert packets == [b"p1", b"p2"]
    assert stream.read_pkt() == b"p3"
