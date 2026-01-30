#!/usr/bin/env python3
"""
Experimental DCM Decoder

This script attempts to decode the CE schema mesh data from 3Shape DCM files.
Based on analysis:
- Facet data uses ~2 bits entropy, values 0-9 dominate (98.7%)
- Vertex data has 8.0 bits entropy (appears encrypted/compressed)
- 3814 vertices for 7353 facets (indexed mesh, good reuse ratio)

Hypothesis:
- Facet encoding uses a variant of Edgebreaker with byte-level symbols
- Vertex encoding uses some form of encryption or advanced compression
"""

import base64
import struct
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import argparse
import os


@dataclass
class Vertex:
    x: float
    y: float
    z: float


@dataclass
class Face:
    v1: int
    v2: int
    v3: int


@dataclass
class Mesh:
    vertices: List[Vertex]
    faces: List[Face]


def load_dcm(file_path: str) -> Tuple[bytes, bytes, int, dict]:
    """Load DCM file and return raw facet/vertex data."""
    with open(file_path, 'r') as f:
        content = f.read()

    root = ET.fromstring(content)
    ce = root.find('.//CE')
    facets = ce.find('Facets')
    vertices = ce.find('Vertices')

    facet_data = base64.b64decode(facets.text.strip())
    vertex_data = base64.b64decode(vertices.text.strip())
    facet_count = int(facets.get('facet_count', 0))

    attrs = {
        'facet_count': facet_count,
        'facet_color': int(facets.get('color', 0)),
        'hps_version': root.get('version'),
        'ce_version': ce.get('version'),
    }

    return facet_data, vertex_data, facet_count, attrs


def analyze_facet_structure(data: bytes, facet_count: int) -> dict:
    """
    Deep analysis of facet data structure.

    The data shows:
    - Bytes 0-3 might be header/count
    - Value 9 appears as potential delimiter (370 times)
    - Values 0,1,2,3 dominate
    """
    results = {}

    # Check if first 4 bytes are a count
    if len(data) >= 4:
        count_le = struct.unpack('<I', data[:4])[0]
        count_be = struct.unpack('>I', data[:4])[0]
        results['first_4_bytes_le'] = count_le
        results['first_4_bytes_be'] = count_be
        results['matches_facet_count'] = count_le == facet_count or count_be == facet_count

    # Look for record boundaries
    # If 9 is a delimiter, check spacing
    positions_9 = [i for i, b in enumerate(data) if b == 9]
    if len(positions_9) > 1:
        gaps = [positions_9[i+1] - positions_9[i] for i in range(len(positions_9)-1)]
        results['delimiter_9_count'] = len(positions_9)
        results['avg_gap'] = sum(gaps) / len(gaps)
        results['min_gap'] = min(gaps)
        results['max_gap'] = max(gaps)

        # Check if gaps correlate with facet count
        results['gaps_vs_facets'] = len(positions_9) / facet_count

    # Analyze byte sequences between delimiters
    # Split on value 9 and analyze segments
    segments = []
    start = 0
    for pos in positions_9:
        if pos > start:
            segments.append(data[start:pos])
        start = pos + 1
    if start < len(data):
        segments.append(data[start:])

    if segments:
        seg_lengths = [len(s) for s in segments]
        results['num_segments'] = len(segments)
        results['avg_segment_len'] = sum(seg_lengths) / len(seg_lengths)

        # Analyze first few segments
        results['first_segments'] = [list(s[:20]) for s in segments[:5]]

    # Try interpreting as variable-length encoded indices
    # Common pattern: small deltas encoded with minimal bits
    results['value_runs'] = analyze_runs(data)

    return results


def analyze_runs(data: bytes) -> dict:
    """Analyze runs of identical or sequential values."""
    runs = []
    current_val = data[0]
    current_run = 1

    for b in data[1:]:
        if b == current_val:
            current_run += 1
        else:
            runs.append((current_val, current_run))
            current_val = b
            current_run = 1
    runs.append((current_val, current_run))

    # Analyze run statistics
    run_lengths = [r[1] for r in runs]
    return {
        'num_runs': len(runs),
        'avg_run_length': sum(run_lengths) / len(run_lengths),
        'max_run_length': max(run_lengths),
        'longest_runs': sorted(runs, key=lambda x: -x[1])[:10]
    }


def try_xor_decrypt(data: bytes, key_sizes: List[int] = [1, 2, 4, 8, 16]) -> dict:
    """
    Try XOR decryption with various key sizes.
    If the data is XOR encrypted, the decrypted version should have lower entropy.
    """
    import math
    results = {}

    def entropy(d):
        if not d:
            return 0
        counter = Counter(d)
        total = len(d)
        return -sum((c/total) * math.log2(c/total) for c in counter.values() if c > 0)

    original_entropy = entropy(data)
    results['original_entropy'] = original_entropy

    for key_size in key_sizes:
        # Try to derive key from known patterns
        # If we know some expected output (e.g., float values near 0), we can derive key

        # Method 1: Assume key repeats and look for patterns
        # XOR with itself shifted by key_size should reveal patterns
        if len(data) > key_size * 2:
            xored = bytes(a ^ b for a, b in zip(data[:-key_size], data[key_size:]))
            xored_entropy = entropy(xored)
            results[f'self_xor_{key_size}'] = xored_entropy

    # Try XOR with common patterns
    common_keys = [
        b'\x00',  # No encryption
        b'\xFF',  # All bits flipped
        b'\xAA',  # Alternating bits
        b'\x55',  # Alternating bits inverse
    ]

    for key in common_keys:
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        dec_entropy = entropy(decrypted)
        results[f'xor_{key.hex()}'] = dec_entropy

    return results


def try_vertex_decodings(vertex_data: bytes, expected_vertices: int) -> List[dict]:
    """
    Try various vertex decoding schemes.
    """
    results = []

    # Scheme 1: Maybe there's a header with bounding box/scale
    # Then quantized integers

    # Check for float32 header (bounding box)
    if len(vertex_data) >= 24:
        potential_bbox = struct.unpack('<ffffff', vertex_data[:24])
        results.append({
            'scheme': 'float32_header_bbox',
            'values': potential_bbox,
            'reasonable': all(-1000 < v < 1000 for v in potential_bbox)
        })

    # Check for double header
    if len(vertex_data) >= 48:
        potential_bbox = struct.unpack('<dddddd', vertex_data[:48])
        results.append({
            'scheme': 'float64_header_bbox',
            'values': potential_bbox,
            'reasonable': all(-1000 < v < 1000 for v in potential_bbox)
        })

    # Check if data after potential header is different
    for header_size in [24, 48, 64, 128]:
        if len(vertex_data) > header_size:
            header = vertex_data[:header_size]
            body = vertex_data[header_size:]

            header_entropy = calculate_entropy(header)
            body_entropy = calculate_entropy(body)

            results.append({
                'scheme': f'header_{header_size}b',
                'header_entropy': header_entropy,
                'body_entropy': body_entropy,
                'entropy_diff': body_entropy - header_entropy
            })

    # Try treating entire data as quantized int16 with scale
    if len(vertex_data) % 6 == 0:
        num_verts = len(vertex_data) // 6
        results.append({
            'scheme': 'int16_vertices',
            'vertex_count': num_verts,
            'matches_expected': num_verts == expected_vertices
        })

        # Sample some int16 triplets
        sample = []
        for i in range(min(10, num_verts)):
            offset = i * 6
            x, y, z = struct.unpack('<hhh', vertex_data[offset:offset+6])
            sample.append((x, y, z))
        results.append({
            'scheme': 'int16_sample',
            'values': sample
        })

    return results


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of data."""
    import math
    if not data:
        return 0
    counter = Counter(data)
    total = len(data)
    return -sum((c/total) * math.log2(c/total) for c in counter.values() if c > 0)


def attempt_facet_decode(facet_data: bytes, facet_count: int) -> Optional[List[Face]]:
    """
    Attempt to decode facet connectivity data.

    Based on analysis:
    - Values 0,1,2,3 dominate (symbols?)
    - Value 9 appears as delimiter
    - Low entropy suggests structured encoding

    Hypothesis: Each "segment" between 9s encodes one or more triangles
    using a corner-table like scheme.
    """
    # Split on delimiter
    segments = []
    current = []
    for b in facet_data:
        if b == 9:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(b)
    if current:
        segments.append(current)

    print(f"Found {len(segments)} segments for {facet_count} faces")
    print(f"Ratio: {len(segments) / facet_count:.2f} segments per face")

    # Analyze segment patterns
    segment_patterns = Counter(tuple(s) for s in segments if len(s) <= 10)
    print(f"Unique short patterns: {len(segment_patterns)}")
    print(f"Most common patterns: {segment_patterns.most_common(10)}")

    # Try interpreting common patterns
    # In Edgebreaker: C=continue, L=left, R=right, S=split, E=end
    # Values 0,1,2,3 might map to these operations

    return None  # Not yet implemented


def write_stl(mesh: Mesh, filename: str):
    """Write mesh to ASCII STL file."""
    with open(filename, 'w') as f:
        f.write("solid mesh\n")
        for face in mesh.faces:
            v1 = mesh.vertices[face.v1]
            v2 = mesh.vertices[face.v2]
            v3 = mesh.vertices[face.v3]

            # Calculate normal (simplified - not normalized)
            # For proper STL you'd normalize this
            f.write("  facet normal 0 0 0\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v1.x} {v1.y} {v1.z}\n")
            f.write(f"      vertex {v2.x} {v2.y} {v2.z}\n")
            f.write(f"      vertex {v3.x} {v3.y} {v3.z}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write("endsolid mesh\n")


def main():
    parser = argparse.ArgumentParser(description='Experimental DCM decoder')
    parser.add_argument('dcm_file', help='Path to DCM file')
    parser.add_argument('--output', '-o', help='Output STL file (if decoding succeeds)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    print("=" * 60)
    print("EXPERIMENTAL DCM DECODER")
    print("=" * 60)
    print()

    facet_data, vertex_data, facet_count, attrs = load_dcm(args.dcm_file)

    print(f"Loaded: {facet_count} faces, {len(facet_data)} facet bytes, {len(vertex_data)} vertex bytes")
    print()

    # Deep facet analysis
    print("## Facet Data Deep Analysis")
    facet_analysis = analyze_facet_structure(facet_data, facet_count)
    for key, value in facet_analysis.items():
        if key != 'first_segments' and key != 'longest_runs':
            print(f"  {key}: {value}")

    if 'first_segments' in facet_analysis:
        print("  First segments:")
        for i, seg in enumerate(facet_analysis['first_segments']):
            print(f"    [{i}]: {seg}")

    print()

    # Vertex encryption analysis
    print("## Vertex Data Encryption Analysis")
    xor_results = try_xor_decrypt(vertex_data)
    for key, value in xor_results.items():
        print(f"  {key}: {value:.4f}")

    print()

    # Vertex decoding attempts
    print("## Vertex Decoding Attempts")
    expected_verts = len(vertex_data) // 12  # Assume float32
    decode_results = try_vertex_decodings(vertex_data, expected_verts)
    for result in decode_results:
        print(f"  {result['scheme']}:")
        for k, v in result.items():
            if k != 'scheme':
                if isinstance(v, tuple) and len(v) > 3:
                    print(f"    {k}: {v[:3]}... (truncated)")
                else:
                    print(f"    {k}: {v}")

    print()

    # Attempt decode
    print("## Decode Attempt")
    faces = attempt_facet_decode(facet_data, facet_count)

    if faces:
        print(f"Successfully decoded {len(faces)} faces!")
        if args.output:
            # Would need vertices too
            print("Note: Full mesh output requires vertex decoding")
    else:
        print("Facet decoding not yet successful - more analysis needed")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
Key observations:
1. Facet data is highly structured (2.08 bits entropy)
   - Uses values 0-9 primarily
   - Value 9 appears to be a delimiter
   - Likely a modified Edgebreaker or corner-table encoding

2. Vertex data appears encrypted or uses advanced compression
   - Maximum entropy (8.0 bits) suggests randomization
   - XOR analysis doesn't show obvious key patterns
   - May use proprietary compression (not zlib/gzip/etc)

Next steps for reverse engineering:
- Compare multiple DCM files to find consistent patterns
- Use dynamic analysis (monitor SDX process)
- Look for known byte sequences (magic numbers, etc.)
- Consider if vertex data uses AES or similar encryption
""")


if __name__ == '__main__':
    main()
