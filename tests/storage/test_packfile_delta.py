
import hashlib
import io
import struct
import zlib
from pathlib import Path
from deep.objects.packfile import PackfileParser

def create_packfile_with_deltas():
    # 1. Base Blob
    base_data = b"Hello, world! This is a base object for delta testing."
    base_header = f"blob {len(base_data)}".encode("ascii") + b"\x00"
    base_sha = hashlib.sha1(base_header + base_data).hexdigest()
    base_compressed = zlib.compress(base_data)
    
    # 2. OFS_DELTA (modifies base)
    # Delta instruction stream:
    # [source size] [target size] [copy from 0, len] [add some text]
    # instruction: copy whole base, then add " OFS delta"
    # Actually, simpler: just a small change.
    delta_data = b"Hello, world! This is a base object for delta testing. OFS delta"
    # Let's use deep.objects.delta.create_delta or just manual
    from deep.objects.delta import create_delta as deep_create_delta
    ofs_delta_content = deep_create_delta(base_data, delta_data)
    ofs_delta_compressed = zlib.compress(ofs_delta_content)
    
    # 3. REF_DELTA (modifies base)
    ref_delta_data = b"Hello, world! This is a base object for delta testing. REF delta"
    ref_delta_content = deep_create_delta(base_data, ref_delta_data)
    ref_delta_compressed = zlib.compress(ref_delta_content)
    
    # Build the packfile bytes
    buf = io.BytesIO()
    # PACK header
    buf.write(b"PACK")
    buf.write(struct.pack(">I", 2)) # version 2
    buf.write(struct.pack(">I", 3)) # 3 objects
    
    # Object 1: Base Blob (Type 3)
    # Header: MSB=0, Type=3, Size = len(base_data)
    def write_header(f, obj_type, size):
        byte = (obj_type << 4) | (size & 15)
        size >>= 4
        while size:
            f.write(struct.pack("B", byte | 0x80))
            byte = size & 127
            size >>= 7
        f.write(struct.pack("B", byte))

    write_header(buf, 3, len(base_data))
    buf.write(base_compressed)
    
    entry2_offset = buf.tell()
    # Object 2: OFS_DELTA (Type 6)
    write_header(buf, 6, len(ofs_delta_content))
    # Negative offset to Object 1
    neg_offset = entry2_offset - 12 # Object 1 starts at 12
    # Encode neg_offset as VLI
    def encode_ofs_offset(n):
        res = bytearray()
        res.append(n & 0x7F)
        n >>= 7
        while n:
            n -= 1
            res.insert(0, (n & 0x7F) | 0x80)
            n >>= 7
        return bytes(res)
    
    buf.write(encode_ofs_offset(neg_offset))
    buf.write(ofs_delta_compressed)
    
    # Object 3: REF_DELTA (Type 7)
    write_header(buf, 7, len(ref_delta_content))
    buf.write(bytes.fromhex(base_sha))
    buf.write(ref_delta_compressed)
    
    # Trailer
    data = buf.getvalue()
    trailer = hashlib.sha1(data).digest()
    buf.write(trailer)
    
    return buf.getvalue(), base_data, delta_data, ref_delta_data

def test_packfile_parsing_with_deltas():
    pack_data, base_expected, ofs_expected, ref_expected = create_packfile_with_deltas()
    
    stream = io.BytesIO(pack_data)
    parser = PackfileParser(stream)
    results = parser.parse()
    
    assert len(results) == 3
    assert results[0] == ("blob", base_expected)
    assert results[1] == ("blob", ofs_expected)
    assert results[2] == ("blob", ref_expected)

if __name__ == "__main__":
    try:
        test_packfile_parsing_with_deltas()
        print("Test passed!")
    except Exception as e:
        import traceback
        traceback.print_exc()
