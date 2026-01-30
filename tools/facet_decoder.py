#!/usr/bin/env python3
"""
Facet Connectivity Decoder

Reverse engineers the CE schema facet encoding using statistical analysis
across multiple DCM/STL pairs.

The facet data appears to use an Edgebreaker-like encoding:
- Low entropy (~2 bits)
- Values 0-9 dominate (98.7%)
- Value 9 appears to be a delimiter/marker
- Compression ratio ~9% of raw indices

This tool:
1. Extracts facet data and corresponding face indices from pairs
2. Builds a statistical model of the encoding
3. Attempts to decode new files

Usage:
    # Train decoder on sample pairs
    python facet_decoder.py train /path/to/pairs --model facet_model.json

    # Decode a file
    python facet_decoder.py decode input.dcm --model facet_model.json

    # Analyze encoding patterns
    python facet_decoder.py analyze /path/to/pairs
"""

import argparse
import base64
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import math


@dataclass
class FacetSample:
    """A sample of facet data with known face indices."""
    dcm_path: str
    facet_count: int
    vertex_count: int
    facet_data: bytes
    face_indices: List[Tuple[int, int, int]]  # From STL


def load_dcm_facet_data(dcm_path: str) -> Tuple[bytes, int]:
    """Load facet data from DCM file."""
    with open(dcm_path, 'r', encoding='utf-8') as f:
        content = f.read()

    root = ET.fromstring(content)
    facets = root.find('.//Facets')

    facet_data = base64.b64decode(facets.text.strip())
    facet_count = int(facets.get('facet_count', 0))

    return facet_data, facet_count


def load_stl_faces(stl_path: str) -> Tuple[List[Tuple[int, int, int]], int]:
    """Load face indices from STL file."""
    with open(stl_path, 'rb') as f:
        data = f.read()

    # Detect format
    if data[:5].lower() == b'solid' and b'facet' in data[:1000]:
        return load_stl_faces_ascii(data)
    else:
        return load_stl_faces_binary(data)


def load_stl_faces_binary(data: bytes) -> Tuple[List[Tuple[int, int, int]], int]:
    """Load faces from binary STL, returning indices into unique vertex list."""
    num_triangles = struct.unpack('<I', data[80:84])[0]

    vertices = []
    vertex_map = {}
    faces = []
    offset = 84

    for _ in range(num_triangles):
        offset += 12  # Skip normal
        face_indices = []
        for _ in range(3):
            x, y, z = struct.unpack('<fff', data[offset:offset+12])
            vertex_key = (round(x, 6), round(y, 6), round(z, 6))
            if vertex_key not in vertex_map:
                vertex_map[vertex_key] = len(vertices)
                vertices.append(vertex_key)
            face_indices.append(vertex_map[vertex_key])
            offset += 12
        offset += 2
        faces.append(tuple(face_indices))

    return faces, len(vertices)


def load_stl_faces_ascii(data: bytes) -> Tuple[List[Tuple[int, int, int]], int]:
    """Load faces from ASCII STL."""
    import re
    content = data.decode('ascii', errors='ignore')

    facet_pattern = re.compile(
        r'facet\s+normal.*?'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)',
        re.IGNORECASE | re.DOTALL
    )

    vertices = []
    vertex_map = {}
    faces = []

    for match in facet_pattern.finditer(content):
        face_indices = []
        for i in range(3):
            x = float(match.group(i*3 + 1))
            y = float(match.group(i*3 + 2))
            z = float(match.group(i*3 + 3))
            vertex_key = (round(x, 6), round(y, 6), round(z, 6))
            if vertex_key not in vertex_map:
                vertex_map[vertex_key] = len(vertices)
                vertices.append(vertex_key)
            face_indices.append(vertex_map[vertex_key])
        faces.append(tuple(face_indices))

    return faces, len(vertices)


def analyze_segment_patterns(samples: List[FacetSample]) -> Dict:
    """Analyze patterns in facet data segments across samples."""
    results = {
        'total_samples': len(samples),
        'segment_analysis': {},
        'byte_patterns': {},
        'header_patterns': {},
    }

    all_segments = []
    segment_to_faces = defaultdict(list)  # Map segment patterns to face deltas

    for sample in samples:
        # Split on delimiter (value 9)
        segments = []
        current = []
        for b in sample.facet_data:
            if b == 9:
                if current:
                    segments.append(tuple(current))
                current = []
            else:
                current.append(b)
        if current:
            segments.append(tuple(current))

        all_segments.extend(segments)

        # Try to correlate segments with face patterns
        # Hypothesis: each segment encodes a sequence of faces
        faces_per_segment = len(sample.face_indices) / len(segments) if segments else 0
        results['segment_analysis'][sample.dcm_path] = {
            'num_segments': len(segments),
            'num_faces': len(sample.face_indices),
            'faces_per_segment': faces_per_segment,
        }

    # Analyze segment patterns
    segment_counter = Counter(all_segments)
    results['unique_segments'] = len(segment_counter)
    results['most_common_segments'] = [
        (list(seg), count) for seg, count in segment_counter.most_common(20)
    ]

    # Analyze segment lengths
    seg_lengths = [len(s) for s in all_segments]
    results['segment_lengths'] = {
        'min': min(seg_lengths) if seg_lengths else 0,
        'max': max(seg_lengths) if seg_lengths else 0,
        'avg': sum(seg_lengths) / len(seg_lengths) if seg_lengths else 0,
    }

    # Analyze first bytes of segments (potential operation codes)
    first_bytes = Counter(s[0] for s in all_segments if s)
    results['segment_first_bytes'] = first_bytes.most_common(10)

    return results


def analyze_edgebreaker_hypothesis(samples: List[FacetSample]) -> Dict:
    """
    Test Edgebreaker encoding hypothesis.

    Edgebreaker uses 5 symbols: C, L, R, S, E
    - C (Continue): Most common, adds one vertex
    - L (Left): Connect to left
    - R (Right): Connect to right
    - S (Split): Start new component
    - E (End): Finish component

    In the DCM data, values 0-3 dominate, which could map to these operations.
    """
    results = {
        'hypothesis': 'Edgebreaker-variant encoding',
        'symbol_analysis': {},
    }

    # Aggregate byte frequencies
    all_bytes = Counter()
    for sample in samples:
        all_bytes.update(sample.facet_data)

    total = sum(all_bytes.values())

    # The top values should map to Edgebreaker symbols
    # C is typically 60-90% of operations
    top_values = all_bytes.most_common(10)
    results['byte_frequencies'] = [
        (val, count, count/total*100) for val, count in top_values
    ]

    # Check if value 0 could be 'C' (most common)
    val_0_pct = all_bytes[0] / total * 100 if total > 0 else 0
    val_1_pct = all_bytes[1] / total * 100 if total > 0 else 0
    val_2_pct = all_bytes[2] / total * 100 if total > 0 else 0
    val_3_pct = all_bytes[3] / total * 100 if total > 0 else 0

    results['symbol_hypothesis'] = {
        0: f'{val_0_pct:.1f}% - likely C (continue) or counter',
        1: f'{val_1_pct:.1f}% - likely L or R',
        2: f'{val_2_pct:.1f}% - likely R or L',
        3: f'{val_3_pct:.1f}% - likely S (split) or E (end)',
        9: f'delimiter/marker between segments',
    }

    # Analyze sequences
    # In Edgebreaker, certain sequences are common
    digrams = Counter()
    trigrams = Counter()

    for sample in samples:
        data = sample.facet_data
        for i in range(len(data) - 1):
            digrams[(data[i], data[i+1])] += 1
        for i in range(len(data) - 2):
            trigrams[(data[i], data[i+1], data[i+2])] += 1

    results['common_digrams'] = [
        (list(seq), count) for seq, count in digrams.most_common(20)
    ]
    results['common_trigrams'] = [
        (list(seq), count) for seq, count in trigrams.most_common(20)
    ]

    return results


def analyze_header_structure(samples: List[FacetSample]) -> Dict:
    """Analyze the header structure of facet data."""
    results = {
        'header_analysis': []
    }

    for sample in samples:
        data = sample.facet_data
        if len(data) < 16:
            continue

        header_info = {
            'dcm': os.path.basename(sample.dcm_path),
            'facet_count': sample.facet_count,
            'vertex_count': sample.vertex_count,
            'first_16_bytes': list(data[:16]),
            'first_16_hex': data[:16].hex(),
        }

        # Try interpreting first bytes as integers
        if len(data) >= 4:
            header_info['first_uint32'] = struct.unpack('<I', data[:4])[0]
            header_info['first_int32'] = struct.unpack('<i', data[:4])[0]

        if len(data) >= 8:
            header_info['second_uint32'] = struct.unpack('<I', data[4:8])[0]

        # Check if any header values match facet/vertex counts
        for i in range(min(16, len(data) - 3)):
            val = struct.unpack('<I', data[i:i+4])[0]
            if val == sample.facet_count:
                header_info['facet_count_at_offset'] = i
            if val == sample.vertex_count:
                header_info['vertex_count_at_offset'] = i

        results['header_analysis'].append(header_info)

    # Look for patterns
    if results['header_analysis']:
        first_bytes = [h['first_16_bytes'] for h in results['header_analysis']]
        # Check which positions are constant across samples
        constant_positions = []
        for pos in range(16):
            values_at_pos = [fb[pos] for fb in first_bytes if len(fb) > pos]
            if len(set(values_at_pos)) == 1:
                constant_positions.append((pos, values_at_pos[0]))
        results['constant_header_positions'] = constant_positions

    return results


def try_decode_facets(facet_data: bytes, facet_count: int, vertex_count: int) -> Optional[List[Tuple[int, int, int]]]:
    """
    Attempt to decode facet connectivity.

    This is experimental - based on pattern analysis.
    """
    # Split into segments
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

    print(f"Facet data: {len(facet_data)} bytes, {len(segments)} segments")
    print(f"Expected: {facet_count} faces, {vertex_count} vertices")
    print(f"Approx faces per segment: {facet_count / len(segments) if segments else 0:.1f}")

    # TODO: Implement actual decoding based on learned patterns
    # This requires more samples to determine the exact encoding scheme

    return None


def main():
    parser = argparse.ArgumentParser(description='Facet connectivity decoder')
    subparsers = parser.add_subparsers(dest='command', help='Command')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze facet patterns')
    analyze_parser.add_argument('path', help='Directory with DCM/STL pairs')
    analyze_parser.add_argument('--limit', type=int, default=100, help='Limit samples')
    analyze_parser.add_argument('--output', '-o', help='Save analysis to JSON')

    # Train command
    train_parser = subparsers.add_parser('train', help='Train decoder model')
    train_parser.add_argument('path', help='Directory with DCM/STL pairs')
    train_parser.add_argument('--model', '-m', required=True, help='Output model file')
    train_parser.add_argument('--limit', type=int, help='Limit samples')

    # Decode command
    decode_parser = subparsers.add_parser('decode', help='Decode a DCM file')
    decode_parser.add_argument('dcm_file', help='DCM file to decode')
    decode_parser.add_argument('--model', '-m', required=True, help='Model file')

    args = parser.parse_args()

    if args.command == 'analyze':
        # Find pairs
        pairs = []
        for root, dirs, files in os.walk(args.path):
            for f in files:
                if f.lower().endswith('.dcm'):
                    dcm_path = os.path.join(root, f)
                    stl_path = os.path.splitext(dcm_path)[0] + '.stl'
                    if os.path.exists(stl_path):
                        pairs.append((dcm_path, stl_path))

        if args.limit:
            pairs = pairs[:args.limit]

        print(f"Found {len(pairs)} pairs")

        # Load samples
        samples = []
        for dcm_path, stl_path in pairs:
            try:
                facet_data, facet_count = load_dcm_facet_data(dcm_path)
                faces, vertex_count = load_stl_faces(stl_path)
                samples.append(FacetSample(
                    dcm_path=dcm_path,
                    facet_count=facet_count,
                    vertex_count=vertex_count,
                    facet_data=facet_data,
                    face_indices=faces,
                ))
            except Exception as e:
                print(f"Error loading {dcm_path}: {e}")

        print(f"Loaded {len(samples)} samples")
        print()

        # Run analyses
        print("=" * 60)
        print("SEGMENT PATTERN ANALYSIS")
        print("=" * 60)
        segment_results = analyze_segment_patterns(samples)

        print(f"Unique segments: {segment_results['unique_segments']}")
        print(f"Segment lengths: {segment_results['segment_lengths']}")
        print(f"\nMost common segments:")
        for seg, count in segment_results['most_common_segments'][:10]:
            print(f"  {seg}: {count}")

        print(f"\nSegment first bytes: {segment_results['segment_first_bytes']}")

        print()
        print("=" * 60)
        print("EDGEBREAKER HYPOTHESIS")
        print("=" * 60)
        eb_results = analyze_edgebreaker_hypothesis(samples)

        print("Byte frequencies:")
        for val, count, pct in eb_results['byte_frequencies']:
            print(f"  {val:3d}: {pct:5.1f}%")

        print("\nSymbol hypothesis:")
        for sym, desc in eb_results['symbol_hypothesis'].items():
            print(f"  {sym}: {desc}")

        print("\nCommon digrams:")
        for seq, count in eb_results['common_digrams'][:10]:
            print(f"  {seq}: {count}")

        print()
        print("=" * 60)
        print("HEADER STRUCTURE ANALYSIS")
        print("=" * 60)
        header_results = analyze_header_structure(samples)

        if header_results['header_analysis']:
            print("First 3 samples:")
            for h in header_results['header_analysis'][:3]:
                print(f"  {h['dcm']}: faces={h['facet_count']}, verts={h['vertex_count']}")
                print(f"    Header: {h['first_16_bytes']}")
                if 'facet_count_at_offset' in h:
                    print(f"    Facet count found at offset: {h['facet_count_at_offset']}")

        if 'constant_header_positions' in header_results:
            print(f"\nConstant header positions: {header_results['constant_header_positions']}")

        # Save if requested
        if args.output:
            all_results = {
                'segments': segment_results,
                'edgebreaker': eb_results,
                'headers': header_results,
            }
            with open(args.output, 'w') as f:
                json.dump(all_results, f, indent=2)
            print(f"\nSaved analysis to {args.output}")

    elif args.command == 'decode':
        print("Decode functionality requires trained model from multiple samples.")
        print("Use 'analyze' command first to understand the encoding.")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
