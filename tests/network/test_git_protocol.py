"""
tests.network.test_git_protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Comprehensive tests for the Git protocol implementation:
- PKT-line encoding/decoding
- Git delta engine (apply/create)
- Packfile parser (v2 format)
- Pack index reader/writer
- Object store operations
- URL parsing
- Ref advertisement parsing
"""

from __future__ import annotations

import hashlib
import io
import struct
import tempfile
import zlib
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════
# 1. PKT-LINE PROTOCOL TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPktLine:
    """Test Git pkt-line wire protocol."""

    def test_write_and_read_roundtrip(self):
        """Verify pkt-line encode/decode roundtrip."""
        from deep.network.pkt_line import write_pkt_line, read_pkt_line

        buf = io.BytesIO()
        write_pkt_line(buf, b"hello world")
        buf.seek(0)

        result = read_pkt_line(buf)
        assert result == b"hello world"

    def test_flush_packet(self):
        """Verify flush packet (0000) returns None."""
        from deep.network.pkt_line import write_flush, read_pkt_line

        buf = io.BytesIO()
        write_flush(buf)
        buf.seek(0)

        result = read_pkt_line(buf)
        assert result is None

    def test_multiple_packets_roundtrip(self):
        """Verify reading multiple packets until flush."""
        from deep.network.pkt_line import (
            write_pkt_line, write_flush, read_pkt_lines,
        )

        buf = io.BytesIO()
        write_pkt_line(buf, b"line 1")
        write_pkt_line(buf, b"line 2")
        write_pkt_line(buf, b"line 3")
        write_flush(buf)
        buf.seek(0)

        lines = read_pkt_lines(buf)
        assert len(lines) == 3
        assert lines[0] == b"line 1"
        assert lines[1] == b"line 2"
        assert lines[2] == b"line 3"

    def test_length_prefix_format(self):
        """Verify the 4-byte hex length prefix."""
        from deep.network.pkt_line import write_pkt_line

        buf = io.BytesIO()
        data = b"test"
        write_pkt_line(buf, data)
        buf.seek(0)
        raw = buf.read()

        # "test\n" is 5 bytes + 4 header = 9 = 0x0009
        assert raw[:4] == b"0009"

    def test_empty_stream_raises_eof(self):
        """Reading from empty stream should raise EOFError."""
        from deep.network.pkt_line import read_pkt_line

        buf = io.BytesIO(b"")
        with pytest.raises(EOFError):
            read_pkt_line(buf)

    def test_large_packet(self):
        """Verify large packets are handled correctly."""
        from deep.network.pkt_line import write_pkt_line, read_pkt_line

        data = b"x" * 60000
        buf = io.BytesIO()
        write_pkt_line(buf, data)
        buf.seek(0)

        result = read_pkt_line(buf)
        assert result == data

    def test_packet_too_large_raises(self):
        """Verify packets exceeding max size raise ValueError."""
        from deep.network.pkt_line import write_pkt_line

        data = b"x" * 70000
        buf = io.BytesIO()
        with pytest.raises(ValueError):
            write_pkt_line(buf, data)


# ═══════════════════════════════════════════════════════════════════
# 2. GIT DELTA ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestDelta:
    """Test Git-compatible delta engine."""

    def test_apply_delta_simple_insert(self):
        """Delta with pure insert instructions."""
        from deep.objects.delta import apply_delta, _encode_varint_le

        source = b"Hello, World!"
        target = b"Hello, Deep World!"

        # Build a simple insert-only delta
        delta = bytearray()
        delta.extend(_encode_varint_le(len(source)))  # source size
        delta.extend(_encode_varint_le(len(target)))  # target size
        # Insert entire target
        pos = 0
        while pos < len(target):
            chunk = min(127, len(target) - pos)
            delta.append(chunk)
            delta.extend(target[pos:pos + chunk])
            pos += chunk

        result = apply_delta(source, bytes(delta))
        assert result == target

    def test_apply_delta_copy(self):
        """Delta with copy instruction."""
        from deep.objects.delta import apply_delta, _encode_varint_le

        source = b"ABCDEFGHIJ" * 10  # 100 bytes
        target = source[:50]  # First 50 bytes

        delta = bytearray()
        delta.extend(_encode_varint_le(len(source)))
        delta.extend(_encode_varint_le(len(target)))

        # Copy: offset=0, size=50
        cmd = 0x80 | 0x01 | 0x10  # offset byte 0, size byte 0
        delta.append(cmd)
        delta.append(0)    # offset = 0
        delta.append(50)   # size = 50

        result = apply_delta(source, bytes(delta))
        assert result == target

    def test_create_and_apply_roundtrip(self):
        """Create a delta and apply it — result should match target."""
        from deep.objects.delta import create_delta, apply_delta

        source = b"The quick brown fox jumps over the lazy dog. " * 20
        target = b"The quick brown fox leaps over the lazy cat. " * 20

        delta = create_delta(source, target)
        result = apply_delta(source, delta)
        assert result == target

    def test_delta_identical_objects(self):
        """Delta of identical objects should produce the same result."""
        from deep.objects.delta import create_delta, apply_delta

        data = b"Hello, World! " * 100
        delta = create_delta(data, data)
        result = apply_delta(data, delta)
        assert result == data

    def test_delta_empty_target_error(self):
        """Applying empty delta should raise."""
        from deep.objects.delta import apply_delta

        with pytest.raises(ValueError):
            apply_delta(b"source", b"")

    def test_delta_source_size_mismatch(self):
        """Delta with wrong source size should fail."""
        from deep.objects.delta import _encode_varint_le

        delta = bytearray()
        delta.extend(_encode_varint_le(999))  # Wrong source size
        delta.extend(_encode_varint_le(5))    # Target size
        delta.append(5)                       # Insert 5 bytes
        delta.extend(b"hello")

        from deep.objects.delta import apply_delta
        with pytest.raises(ValueError, match="source size"):
            apply_delta(b"short", bytes(delta))


# ═══════════════════════════════════════════════════════════════════
# 3. PACKFILE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPackfile:
    """Test Git v2 packfile parser and writer."""

    def test_build_and_parse_roundtrip(self):
        """Build a packfile and parse it back."""
        from deep.objects.packfile import build_pack, parse_packfile

        objects = [
            ("blob", b"Hello, World!"),
            ("blob", b"Second blob content"),
            ("blob", b"Third blob for testing"),
        ]

        pack_data = build_pack(objects)

        # Verify PACK signature
        assert pack_data[:4] == b"PACK"

        # Verify version
        version = struct.unpack(">I", pack_data[4:8])[0]
        assert version == 2

        # Verify count
        count = struct.unpack(">I", pack_data[8:12])[0]
        assert count == 3

        # Parse back
        parsed = parse_packfile(pack_data)
        assert len(parsed) == 3
        for (orig_type, orig_data), (parsed_type, parsed_data) in zip(
            objects, parsed
        ):
            assert parsed_type == orig_type
            assert parsed_data == orig_data

    def test_build_pack_with_different_types(self):
        """Build pack with commit, tree, blob, tag objects."""
        from deep.objects.packfile import build_pack, parse_packfile

        # Create a real tree object content
        tree_content = b"100644 hello.txt\x00" + b"\x00" * 20

        # Create a real commit content
        commit_content = (
            b"tree " + b"a" * 40 + b"\n"
            b"author Test <test@test> 1234567890 +0000\n"
            b"committer Test <test@test> 1234567890 +0000\n"
            b"\n"
            b"Initial commit"
        )

        objects = [
            ("blob", b"file content"),
            ("tree", tree_content),
            ("commit", commit_content),
        ]

        pack_data = build_pack(objects)
        parsed = parse_packfile(pack_data)

        assert len(parsed) == 3
        assert parsed[0][0] == "blob"
        assert parsed[1][0] == "tree"
        assert parsed[2][0] == "commit"

    def test_empty_pack(self):
        """Pack with zero objects."""
        from deep.objects.packfile import build_pack, parse_packfile

        pack_data = build_pack([])
        parsed = parse_packfile(pack_data)
        assert len(parsed) == 0

    def test_unpack_to_store(self):
        """Test unpacking packfile to object store."""
        from deep.objects.packfile import build_pack, unpack_to_store
        from deep.objects.hash_object import read_raw_object, hash_object

        objects = [
            ("blob", b"test content for unpack"),
            ("blob", b"another test blob"),
        ]

        pack_data = build_pack(objects)

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            count = unpack_to_store(pack_data, objects_dir)
            assert count == 2

            # Verify objects are readable
            for obj_type, data in objects:
                sha = hash_object(data, obj_type)
                read_type, read_data = read_raw_object(objects_dir, sha)
                assert read_type == obj_type
                assert read_data == data


# ═══════════════════════════════════════════════════════════════════
# 4. PACK INDEX TESTS
# ═══════════════════════════════════════════════════════════════════

class TestPackIndex:
    """Test Git pack index v2 reader/writer."""

    def test_create_and_read_index(self):
        """Create an index and query it."""
        from deep.objects.pack_index import PackIndex, PackIndexWriter

        entries = [
            ("a" * 40, 0, 12345),
            ("b" * 40, 100, 67890),
            ("c" * 40, 200, 11111),
        ]
        pack_sha = b"\x00" * 20

        idx_data = PackIndexWriter.create(entries, pack_sha)

        with tempfile.NamedTemporaryFile(suffix=".idx", delete=False) as f:
            f.write(idx_data)
            f.flush()

            idx = PackIndex(Path(f.name))
            assert idx.count == 3

            assert idx.find_offset("a" * 40) == 0
            assert idx.find_offset("b" * 40) == 100
            assert idx.find_offset("c" * 40) == 200
            assert idx.find_offset("d" * 40) is None

            shas = idx.all_shas()
            assert len(shas) == 3

        Path(f.name).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# 5. OBJECT STORE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestObjectStore:
    """Test Git-format object store operations."""

    def test_write_and_read_blob(self):
        """Write and read a blob object."""
        from deep.objects.hash_object import write_object, read_raw_object, hash_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            data = b"Hello, Deep Git!"
            sha = write_object(objects_dir, data, "blob")
            expected_sha = hash_object(data, "blob")
            assert sha == expected_sha

            obj_type, content = read_raw_object(objects_dir, sha)
            assert obj_type == "blob"
            assert content == data

    def test_write_and_read_tree(self):
        """Write and read a tree object."""
        from deep.objects.hash_object import write_object, read_raw_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            # Write a blob first
            blob_data = b"file content"
            blob_sha = write_object(objects_dir, blob_data, "blob")

            # Create tree content
            tree_data = b"100644 test.txt\x00" + bytes.fromhex(blob_sha)
            tree_sha = write_object(objects_dir, tree_data, "tree")

            obj_type, content = read_raw_object(objects_dir, tree_sha)
            assert obj_type == "tree"
            assert content == tree_data

    def test_write_and_read_commit(self):
        """Write and read a commit object."""
        from deep.objects.hash_object import write_object, read_raw_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            commit_data = (
                "tree " + "a" * 40 + "\n"
                "author Test User <test@example.com> 1234567890 +0000\n"
                "committer Test User <test@example.com> 1234567890 +0000\n"
                "\n"
                "Test commit message"
            ).encode("utf-8")

            sha = write_object(objects_dir, commit_data, "commit")
            obj_type, content = read_raw_object(objects_dir, sha)
            assert obj_type == "commit"
            assert content == commit_data

    def test_object_exists(self):
        """Test object existence check."""
        from deep.objects.hash_object import write_object, object_exists

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            sha = write_object(objects_dir, b"test data", "blob")
            assert object_exists(objects_dir, sha)
            assert not object_exists(objects_dir, "0" * 40)

    def test_hash_matches_git(self):
        """Verify our hashing produces same result as git would."""
        from deep.objects.hash_object import hash_object

        # Git: echo -n "Hello" | git hash-object --stdin
        # Expected: "blob 5\0Hello" → SHA-1
        data = b"Hello"
        expected_store = b"blob 5\x00Hello"
        expected_sha = hashlib.sha1(expected_store).hexdigest()

        sha = hash_object(data, "blob")
        assert sha == expected_sha

    def test_corrupt_object_detected(self):
        """Corrupt object should be detected on read."""
        from deep.objects.hash_object import write_object, read_raw_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            sha = write_object(objects_dir, b"original", "blob")

            # Corrupt the file
            obj_path = objects_dir / sha[0:2] / sha[2:]
            obj_path.write_bytes(zlib.compress(b"blob 7\x00corrupt"))

            with pytest.raises(ValueError, match="hash mismatch"):
                read_raw_object(objects_dir, sha)


# ═══════════════════════════════════════════════════════════════════
# 6. URL PARSING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestURLParsing:
    """Test Git URL parsing."""

    def test_ssh_scp_style(self):
        """Parse git@host:user/repo.git format."""
        from deep.network.transport import parse_git_url

        transport, host, port, path = parse_git_url(
            "git@github.com:user/repo.git"
        )
        assert transport == "ssh"
        assert host == "git@github.com"
        assert path == "/user/repo.git"

    def test_ssh_url_style(self):
        """Parse ssh://git@host/path format."""
        from deep.network.transport import parse_git_url

        transport, host, port, path = parse_git_url(
            "ssh://git@github.com/user/repo.git"
        )
        assert transport == "ssh"
        assert "github.com" in host

    def test_https_url(self):
        """Parse https://host/path format."""
        from deep.network.transport import parse_git_url

        transport, host, port, path = parse_git_url(
            "https://github.com/user/repo.git"
        )
        assert transport == "https"
        assert host == "github.com"
        assert path == "/user/repo.git"

    def test_http_url(self):
        """Parse http URL."""
        from deep.network.transport import parse_git_url

        transport, host, port, path = parse_git_url(
            "http://gitlab.com/user/repo.git"
        )
        assert transport == "http"
        assert host == "gitlab.com"

    def test_https_with_port(self):
        """Parse HTTPS URL with custom port."""
        from deep.network.transport import parse_git_url

        transport, host, port, path = parse_git_url(
            "https://git.example.com:8443/repo.git"
        )
        assert transport == "https"
        assert port == "8443"


# ═══════════════════════════════════════════════════════════════════
# 7. REF ADVERTISEMENT PARSING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRefAdvertisement:
    """Test Git ref advertisement parsing."""

    def test_parse_simple_refs(self):
        """Parse a simple ref advertisement."""
        from deep.network.smart_protocol import parse_ref_advertisement
        from deep.network.pkt_line import write_pkt_line, write_flush

        buf = io.BytesIO()
        # Service announcement
        write_pkt_line(buf, b"# service=git-upload-pack")
        write_flush(buf)
        # First ref with capabilities
        sha = "a" * 40
        write_pkt_line(buf, f"{sha} HEAD\x00multi_ack side-band-64k".encode())
        write_pkt_line(buf, f"{'b' * 40} refs/heads/main".encode())
        write_flush(buf)

        buf.seek(0)
        refs, caps = parse_ref_advertisement(buf.read())

        assert "HEAD" in refs
        assert refs["HEAD"] == "a" * 40
        assert "refs/heads/main" in refs
        assert "multi_ack" in caps
        assert "side-band-64k" in caps

    def test_parse_empty_repo(self):
        """Parse advertisement from empty repo."""
        from deep.network.smart_protocol import parse_ref_advertisement
        from deep.network.pkt_line import write_pkt_line, write_flush

        buf = io.BytesIO()
        write_pkt_line(buf, b"# service=git-upload-pack")
        write_flush(buf)
        # Zero-SHA capabilities-only line
        write_pkt_line(
            buf, f"{'0' * 40} capabilities^{{}}\x00agent=git/2.43.0".encode()
        )
        write_flush(buf)

        buf.seek(0)
        refs, caps = parse_ref_advertisement(buf.read())
        assert "agent=git/2.43.0" in caps


# ═══════════════════════════════════════════════════════════════════
# 8. FSCK TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFsck:
    """Test object store integrity checking."""

    def test_fsck_healthy_repo(self):
        """Fsck on a healthy repo should return no errors."""
        from deep.objects.fsck import fsck
        from deep.objects.hash_object import write_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            write_object(objects_dir, b"test content", "blob")
            errors = fsck(objects_dir)
            assert len(errors) == 0

    def test_fsck_detects_corruption(self):
        """Fsck should detect corrupted objects."""
        from deep.objects.fsck import fsck
        from deep.objects.hash_object import write_object

        with tempfile.TemporaryDirectory() as tmpdir:
            objects_dir = Path(tmpdir) / "objects"
            objects_dir.mkdir()

            sha = write_object(objects_dir, b"original", "blob")

            # Corrupt it
            obj_path = objects_dir / sha[0:2] / sha[2:]
            obj_path.write_bytes(zlib.compress(b"blob 7\x00corrupt"))

            errors = fsck(objects_dir)
            assert any(e.severity == "error" for e in errors)


# ═══════════════════════════════════════════════════════════════════
# 9. COMMIT FORMAT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCommitFormat:
    """Test Git-compatible commit format."""

    def test_commit_without_sequence_is_git_compatible(self):
        """Commits with sequence_id=0 should not have x-deep-sequence header."""
        from deep.storage.objects import Commit

        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author="Test <test@test>",
            committer="Test <test@test>",
            message="test",
            timestamp=1234567890,
            timezone="+0000",
            sequence_id=0,
        )
        content = commit.serialize_content().decode("utf-8")
        assert "x-deep-sequence" not in content
        assert "sequence" not in content

    def test_commit_with_sequence_uses_x_deep_header(self):
        """Commits with sequence_id > 0 use x-deep-sequence header."""
        from deep.storage.objects import Commit

        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author="Test <test@test>",
            committer="Test <test@test>",
            message="test",
            timestamp=1234567890,
            timezone="+0000",
            sequence_id=42,
        )
        content = commit.serialize_content().decode("utf-8")
        assert "x-deep-sequence 42" in content

    def test_commit_roundtrip_preserves_sequence(self):
        """Commit serialize → parse roundtrip preserves sequence."""
        from deep.storage.objects import Commit

        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=["b" * 40],
            author="Test <test@test>",
            committer="Test <test@test>",
            message="test message",
            timestamp=1234567890,
            timezone="+0200",
            sequence_id=7,
        )
        serialized = commit.serialize_content()
        parsed = Commit.from_content(serialized)

        assert parsed.tree_sha == commit.tree_sha
        assert parsed.parent_shas == commit.parent_shas
        assert parsed.author == commit.author
        assert parsed.message == commit.message
        assert parsed.sequence_id == 7

    def test_commit_hash_matches_git_format(self):
        """Verify commit hashing produces correct SHA-1."""
        from deep.storage.objects import Commit
        from deep.objects.hash_object import hash_object

        commit = Commit(
            tree_sha="a" * 40,
            parent_shas=[],
            author="Test <test@test>",
            committer="Test <test@test>",
            message="test",
            timestamp=1234567890,
            timezone="+0000",
            sequence_id=0,
        )
        content = commit.serialize_content()

        # Verify it matches our hash function
        expected_sha = hash_object(content, "commit")
        assert commit.sha == expected_sha


# ═══════════════════════════════════════════════════════════════════
# 10. AUTH TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAuth:
    """Test authentication module."""

    def test_basic_auth_header(self):
        """Verify Basic auth header format."""
        from deep.network.auth import basic_auth_header

        header = basic_auth_header("user", "pass")
        assert header.startswith("Basic ")
        import base64
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        assert decoded == "user:pass"

    def test_sanitize_url(self):
        """Verify URL sanitization removes credentials."""
        from deep.network.auth import sanitize_url_for_logging

        url = "https://user:secret_token@github.com/repo.git"
        safe = sanitize_url_for_logging(url)
        assert "secret_token" not in safe
        assert "***" in safe
        assert "github.com" in safe

    def test_sanitize_url_without_creds(self):
        """URLs without creds should pass through unchanged."""
        from deep.network.auth import sanitize_url_for_logging

        url = "https://github.com/user/repo.git"
        assert sanitize_url_for_logging(url) == url
