from deep.storage.delta import create_delta, apply_delta

def test_delta_roundtrip():
    source = b"Hello world! This is a test file for delta compression. It has some common parts."
    target = b"Hello world! This is a NEW test file for delta compression. It has some common parts and some extra data at the end."
    
    delta = create_delta(source, target)
    print(f"Source size: {len(source)}")
    print(f"Target size: {len(target)}")
    print(f"Delta size:  {len(delta)}")
    
    reconstructed = apply_delta(source, delta)
    assert reconstructed == target
    print("Delta round-trip: SUCCESS")

    # Test with identical data
    delta_ident = create_delta(source, source)
    assert apply_delta(source, delta_ident) == source
    print("Identical data delta: SUCCESS")
    
    # Test with totally different data
    diff = b"Totally different stuff here."
    delta_diff = create_delta(source, diff)
    assert apply_delta(source, delta_diff) == diff
    print("Different data delta: SUCCESS")

if __name__ == "__main__":
    test_delta_roundtrip()
