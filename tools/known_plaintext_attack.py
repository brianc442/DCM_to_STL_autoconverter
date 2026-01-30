#!/usr/bin/env python3
"""
Known-Plaintext Attack on DCM Vertex Encoding

Since we have:
- Encrypted/encoded DCM vertex data (45,768 bytes)
- Decrypted STL vertex data (45,768 bytes) - SAME SIZE!

We can perform a known-plaintext attack to discover the transformation.

This script:
1. XORs DCM and STL data to find potential key
2. Analyzes key for repeating patterns
3. Tests various cipher hypotheses
4. Validates findings by attempting decryption
"""

import base64
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import argparse
import math
import os


def load_dcm_vertices(dcm_path: str) -> bytes:
    """Load raw vertex data from DCM file."""
    with open(dcm_path, 'r') as f:
        content = f.read()
    root = ET.fromstring(content)
    vertices = root.find('.//CE/Vertices')
    return base64.b64decode(vertices.text.strip())


def load_stl_vertices(stl_path: str) -> bytes:
    """Load raw vertex data from binary STL file."""
    with open(stl_path, 'rb') as f:
        data = f.read()

    # Binary STL: 80 byte header, 4 byte count, then triangles
    num_triangles = struct.unpack('<I', data[80:84])[0]

    # Extract unique vertices in order they appear
    vertices = []
    vertex_set = set()
    offset = 84

    for _ in range(num_triangles):
        offset += 12  # Skip normal
        for _ in range(3):
            vertex_bytes = data[offset:offset+12]
            x, y, z = struct.unpack('<fff', vertex_bytes)
            vertex_key = (round(x, 6), round(y, 6), round(z, 6))
            if vertex_key not in vertex_set:
                vertex_set.add(vertex_key)
                vertices.append((x, y, z))
            offset += 12
        offset += 2  # Skip attribute

    # Convert to raw bytes
    result = b''
    for x, y, z in vertices:
        result += struct.pack('<fff', x, y, z)

    return result


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy."""
    if not data:
        return 0
    counter = Counter(data)
    total = len(data)
    return -sum((c/total) * math.log2(c/total) for c in counter.values() if c > 0)


def find_repeating_pattern(data: bytes, min_len: int = 1, max_len: int = 256) -> dict:
    """Find if data has a repeating pattern."""
    results = {}

    for pattern_len in range(min_len, min(max_len, len(data) // 2) + 1):
        pattern = data[:pattern_len]
        matches = True

        for i in range(pattern_len, len(data)):
            if data[i] != pattern[i % pattern_len]:
                matches = False
                break

        if matches:
            results[pattern_len] = pattern
            # Found shortest repeating pattern
            break

    return results


def analyze_xor_key(key: bytes) -> dict:
    """Analyze the XOR key for patterns."""
    results = {
        'length': len(key),
        'entropy': calculate_entropy(key),
        'unique_bytes': len(set(key)),
    }

    # Check for repeating patterns
    repeating = find_repeating_pattern(key)
    if repeating:
        shortest = min(repeating.keys())
        results['repeating_pattern_length'] = shortest
        results['repeating_pattern'] = repeating[shortest][:64]  # First 64 bytes

    # Check byte distribution
    counter = Counter(key)
    results['most_common_bytes'] = counter.most_common(10)

    # Check for runs of same byte
    runs = []
    current_byte = key[0]
    current_run = 1
    for b in key[1:]:
        if b == current_byte:
            current_run += 1
        else:
            if current_run > 3:
                runs.append((current_byte, current_run))
            current_byte = b
            current_run = 1
    if current_run > 3:
        runs.append((current_byte, current_run))
    results['long_runs'] = runs[:10]

    # Check if key might be derived from position
    # (e.g., key[i] = f(i) for some function f)
    position_correlations = []
    for i in range(min(100, len(key))):
        position_correlations.append((i, key[i], key[i] ^ (i & 0xFF)))
    results['position_samples'] = position_correlations[:20]

    return results


def try_byte_substitution(dcm_data: bytes, stl_data: bytes) -> dict:
    """Check if transformation is a byte substitution cipher."""
    # Build substitution table
    sub_table = {}
    reverse_table = {}
    conflicts = []

    for i, (d, s) in enumerate(zip(dcm_data, stl_data)):
        if d in sub_table:
            if sub_table[d] != s:
                conflicts.append((i, d, sub_table[d], s))
        else:
            sub_table[d] = s

        if s in reverse_table:
            if reverse_table[s] != d:
                pass  # Multiple DCM bytes map to same STL byte (lossy)
        else:
            reverse_table[s] = d

    return {
        'is_substitution': len(conflicts) == 0,
        'table_size': len(sub_table),
        'conflicts': conflicts[:20],
        'substitution_table': sub_table if len(conflicts) == 0 else None,
    }


def try_block_cipher_detection(dcm_data: bytes, stl_data: bytes) -> dict:
    """Check for block cipher patterns."""
    results = {}

    # Common block sizes: 8, 16, 32 bytes
    for block_size in [8, 16, 32, 64]:
        if len(dcm_data) % block_size != 0:
            continue

        num_blocks = len(dcm_data) // block_size

        # Check if identical DCM blocks produce identical STL blocks
        dcm_blocks = {}
        consistent = True

        for i in range(num_blocks):
            start = i * block_size
            end = start + block_size
            dcm_block = dcm_data[start:end]
            stl_block = stl_data[start:end]

            if dcm_block in dcm_blocks:
                if dcm_blocks[dcm_block] != stl_block:
                    consistent = False
                    break
            else:
                dcm_blocks[dcm_block] = stl_block

        results[f'block_{block_size}'] = {
            'consistent': consistent,
            'unique_blocks': len(dcm_blocks),
        }

    return results


def analyze_float_transformation(dcm_data: bytes, stl_data: bytes) -> dict:
    """Analyze if transformation operates on float level."""
    results = {}

    num_floats = len(dcm_data) // 4

    # Extract as float32
    dcm_floats = []
    stl_floats = []

    for i in range(num_floats):
        offset = i * 4
        try:
            dcm_f = struct.unpack('<f', dcm_data[offset:offset+4])[0]
            stl_f = struct.unpack('<f', stl_data[offset:offset+4])[0]
            dcm_floats.append(dcm_f)
            stl_floats.append(stl_f)
        except struct.error:
            break

    # Check for linear transformation: stl = a * dcm + b
    # Sample some points
    valid_pairs = [(d, s) for d, s in zip(dcm_floats, stl_floats)
                   if math.isfinite(d) and math.isfinite(s) and abs(d) > 1e-10]

    if len(valid_pairs) >= 2:
        # Try to find linear coefficients
        ratios = [s/d for d, s in valid_pairs[:100] if abs(d) > 1e-6]
        if ratios:
            results['ratio_samples'] = ratios[:10]
            results['ratio_variance'] = max(ratios) - min(ratios) if ratios else 0

    return results


def analyze_vertex_by_vertex(dcm_data: bytes, stl_data: bytes) -> dict:
    """Analyze transformation at vertex level (12 bytes = 3 floats)."""
    results = {}

    num_vertices = len(dcm_data) // 12

    # XOR at vertex level
    vertex_keys = []
    for i in range(min(100, num_vertices)):
        offset = i * 12
        dcm_vertex = dcm_data[offset:offset+12]
        stl_vertex = stl_data[offset:offset+12]
        key = bytes(a ^ b for a, b in zip(dcm_vertex, stl_vertex))
        vertex_keys.append(key)

    # Check if all vertex keys are the same
    unique_keys = set(vertex_keys)
    results['unique_vertex_keys'] = len(unique_keys)
    results['same_key_per_vertex'] = len(unique_keys) == 1

    if len(unique_keys) == 1:
        results['vertex_key'] = list(vertex_keys[0])

    # Check if key varies predictably with vertex index
    if len(unique_keys) > 1:
        # Look for pattern in how keys differ
        key_diffs = []
        for i in range(1, len(vertex_keys)):
            diff = bytes(a ^ b for a, b in zip(vertex_keys[i], vertex_keys[i-1]))
            key_diffs.append(diff)

        unique_diffs = set(key_diffs)
        results['unique_key_diffs'] = len(unique_diffs)
        if len(unique_diffs) <= 5:
            results['key_diff_pattern'] = [list(d) for d in list(unique_diffs)[:5]]

    return results


def perform_known_plaintext_attack(dcm_path: str, stl_path: str) -> dict:
    """Main attack function."""
    print("=" * 70)
    print("KNOWN-PLAINTEXT ATTACK ON DCM VERTEX ENCODING")
    print("=" * 70)
    print()

    # Load data
    print("Loading data...")
    dcm_data = load_dcm_vertices(dcm_path)
    stl_data = load_stl_vertices(stl_path)

    print(f"  DCM vertex data: {len(dcm_data)} bytes")
    print(f"  STL vertex data: {len(stl_data)} bytes")

    if len(dcm_data) != len(stl_data):
        print(f"  WARNING: Size mismatch! DCM={len(dcm_data)}, STL={len(stl_data)}")
        min_len = min(len(dcm_data), len(stl_data))
        dcm_data = dcm_data[:min_len]
        stl_data = stl_data[:min_len]
        print(f"  Using first {min_len} bytes")

    print()

    # XOR attack
    print("## XOR Analysis")
    xor_key = bytes(a ^ b for a, b in zip(dcm_data, stl_data))
    key_analysis = analyze_xor_key(xor_key)

    print(f"  Key entropy: {key_analysis['entropy']:.4f} bits (8.0 = random)")
    print(f"  Unique bytes in key: {key_analysis['unique_bytes']}")

    if 'repeating_pattern_length' in key_analysis:
        print(f"  REPEATING PATTERN FOUND! Length: {key_analysis['repeating_pattern_length']}")
        print(f"  Pattern (hex): {key_analysis['repeating_pattern'].hex()}")
    else:
        print("  No simple repeating pattern found")

    print(f"  Most common key bytes: {key_analysis['most_common_bytes'][:5]}")
    print()

    # Substitution cipher check
    print("## Substitution Cipher Analysis")
    sub_analysis = try_byte_substitution(dcm_data, stl_data)
    print(f"  Is simple substitution: {sub_analysis['is_substitution']}")
    print(f"  Substitution table size: {sub_analysis['table_size']}")
    if sub_analysis['conflicts']:
        print(f"  Conflicts found: {len(sub_analysis['conflicts'])}")
        print(f"  First conflict: {sub_analysis['conflicts'][0]}")
    print()

    # Block cipher check
    print("## Block Cipher Analysis")
    block_analysis = try_block_cipher_detection(dcm_data, stl_data)
    for block_size, info in block_analysis.items():
        print(f"  {block_size}: consistent={info['consistent']}, unique_blocks={info['unique_blocks']}")
    print()

    # Vertex-level analysis
    print("## Vertex-Level Analysis (12 bytes per vertex)")
    vertex_analysis = analyze_vertex_by_vertex(dcm_data, stl_data)
    print(f"  Unique vertex XOR keys: {vertex_analysis['unique_vertex_keys']}")
    print(f"  Same key for all vertices: {vertex_analysis['same_key_per_vertex']}")

    if vertex_analysis['same_key_per_vertex'] and 'vertex_key' in vertex_analysis:
        print(f"  Vertex key (12 bytes): {vertex_analysis['vertex_key']}")
        print(f"  Vertex key (hex): {bytes(vertex_analysis['vertex_key']).hex()}")

    if 'key_diff_pattern' in vertex_analysis:
        print(f"  Key diff patterns: {vertex_analysis['key_diff_pattern']}")
    print()

    # Save results
    results = {
        'dcm_path': dcm_path,
        'stl_path': stl_path,
        'dcm_size': len(dcm_data),
        'stl_size': len(stl_data),
        'xor_key_entropy': key_analysis['entropy'],
        'xor_key_unique_bytes': key_analysis['unique_bytes'],
        'has_repeating_pattern': 'repeating_pattern_length' in key_analysis,
        'is_substitution_cipher': sub_analysis['is_substitution'],
        'vertex_analysis': vertex_analysis,
    }

    if 'repeating_pattern_length' in key_analysis:
        results['pattern_length'] = key_analysis['repeating_pattern_length']
        results['pattern_hex'] = key_analysis['repeating_pattern'].hex()

    # Try to decrypt with discovered key
    print("## Decryption Validation")

    if 'repeating_pattern_length' in key_analysis:
        pattern = key_analysis['repeating_pattern']
        pattern_len = len(pattern)

        # Decrypt DCM using discovered key
        decrypted = bytes(dcm_data[i] ^ pattern[i % pattern_len] for i in range(len(dcm_data)))

        # Compare with STL
        match_count = sum(1 for a, b in zip(decrypted, stl_data) if a == b)
        match_pct = match_count / len(stl_data) * 100

        print(f"  Decryption match: {match_pct:.2f}%")
        results['decryption_match_pct'] = match_pct

        if match_pct > 99.9:
            print("  SUCCESS! XOR key discovered!")
            results['success'] = True
            results['key'] = pattern.hex()

    else:
        # Try with full XOR key
        decrypted = bytes(dcm_data[i] ^ xor_key[i] for i in range(len(dcm_data)))
        match_count = sum(1 for a, b in zip(decrypted, stl_data) if a == b)
        match_pct = match_count / len(stl_data) * 100
        print(f"  Full XOR decryption match: {match_pct:.2f}%")

        if match_pct == 100:
            print("  XOR with position-dependent key works!")
            print("  Analyzing key structure...")

            # The key IS the XOR of DCM and STL
            # Now analyze its structure
            results['full_key_works'] = True

    print()
    print("=" * 70)

    return results, xor_key


def save_key_file(key: bytes, output_path: str):
    """Save discovered key to file."""
    with open(output_path, 'wb') as f:
        f.write(key)
    print(f"Key saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Known-plaintext attack on DCM encoding')
    parser.add_argument('dcm_file', help='Path to DCM file')
    parser.add_argument('stl_file', help='Path to STL file (SDX output)')
    parser.add_argument('--output-dir', '-o', help='Output directory for results')

    args = parser.parse_args()

    results, xor_key = perform_known_plaintext_attack(args.dcm_file, args.stl_file)

    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save XOR key
        save_key_file(xor_key, str(output_dir / "xor_key.bin"))

        # Save results
        import json
        with open(output_dir / "attack_results.json", 'w') as f:
            # Convert non-serializable items
            serializable = {k: v for k, v in results.items()
                          if not isinstance(v, bytes)}
            json.dump(serializable, f, indent=2)

        print(f"\nResults saved to: {output_dir}")


if __name__ == '__main__':
    main()
