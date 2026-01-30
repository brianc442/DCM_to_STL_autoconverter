#!/usr/bin/env python3
"""
DCM File Format Analyzer

This tool analyzes 3Shape DCM files to reverse engineer the binary format.
DCM files are XML-based (HPS format from HOOPS/Tech Soft 3D) containing
base64-encoded compressed mesh data.

Based on analysis, the format uses:
- XML wrapper with HPS (HOOPS Publish Stream) structure
- "CE" schema for mesh encoding
- Likely Edgebreaker or similar for connectivity compression
- Custom vertex position encoding

Usage:
    python dcm_analyzer.py <dcm_file> [--output-dir <dir>]
"""

import argparse
import base64
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any


@dataclass
class DCMAnalysis:
    """Results of DCM file analysis."""
    file_path: str
    file_size: int
    hps_version: str
    schema: str
    ce_version: str
    facet_count: int
    facet_color: int
    facet_bytes: int
    vertex_bytes: int
    facet_data: bytes
    vertex_data: bytes
    properties: Dict[str, str]
    signature_hash: str


def parse_dcm_file(file_path: str) -> DCMAnalysis:
    """Parse a DCM file and extract its components."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    file_size = os.path.getsize(file_path)
    root = ET.fromstring(content)

    # Extract HPS version
    hps_version = root.get('version', 'unknown')

    # Navigate to packed geometry
    packed_geom = root.find('Packed_geometry')
    schema = packed_geom.find('Schema').text if packed_geom.find('Schema') is not None else 'unknown'

    # Find CE element
    binary_data = packed_geom.find('Binary_data')
    ce = binary_data.find('CE')
    ce_version = ce.get('version', 'unknown')

    # Extract facet data
    facets = ce.find('Facets')
    facet_count = int(facets.get('facet_count', 0))
    facet_color = int(facets.get('color', 0))
    facet_bytes_attr = int(facets.get('base64_encoded_bytes', 0))
    facet_data = base64.b64decode(facets.text.strip())

    # Extract vertex data
    vertices = ce.find('Vertices')
    vertex_bytes_attr = int(vertices.get('base64_encoded_bytes', 0))
    vertex_data = base64.b64decode(vertices.text.strip())

    # Extract properties
    properties = {}
    props_elem = root.find('Properties')
    if props_elem is not None:
        for prop in props_elem.findall('Property'):
            name = prop.get('name', '')
            value = prop.get('value', '')
            properties[name] = value

    # Extract signature hash
    sig_hash = root.find('SignatureHash')
    signature_hash = sig_hash.text if sig_hash is not None else ''

    return DCMAnalysis(
        file_path=file_path,
        file_size=file_size,
        hps_version=hps_version,
        schema=schema,
        ce_version=ce_version,
        facet_count=facet_count,
        facet_color=facet_color,
        facet_bytes=len(facet_data),
        vertex_bytes=len(vertex_data),
        facet_data=facet_data,
        vertex_data=vertex_data,
        properties=properties,
        signature_hash=signature_hash
    )


def analyze_byte_distribution(data: bytes, name: str) -> Dict[str, Any]:
    """Analyze the byte distribution of binary data."""
    counter = Counter(data)
    unique_values = len(counter)
    total_bytes = len(data)

    # Calculate entropy
    import math
    entropy = 0
    for count in counter.values():
        if count > 0:
            p = count / total_bytes
            entropy -= p * math.log2(p)

    # Most common bytes
    most_common = counter.most_common(20)

    # Value range analysis
    min_val = min(data)
    max_val = max(data)

    # Check for patterns suggesting specific encodings
    low_value_ratio = sum(counter[i] for i in range(10)) / total_bytes

    return {
        'name': name,
        'total_bytes': total_bytes,
        'unique_values': unique_values,
        'entropy': entropy,
        'max_entropy': 8.0,  # For reference
        'compression_ratio': entropy / 8.0,
        'most_common': most_common,
        'min_value': min_val,
        'max_value': max_val,
        'low_value_ratio': low_value_ratio,  # Ratio of bytes with value 0-9
    }


def analyze_edgebreaker_patterns(facet_data: bytes, facet_count: int) -> Dict[str, Any]:
    """
    Analyze facet data for Edgebreaker-like patterns.

    Edgebreaker uses 5 symbols: C, L, R, S, E
    Common encoding: C=0 (1 bit), others use 1 + 2 bits

    The byte distribution showing dominance of 0,1,2,3 values
    suggests variable-length or nibble-based encoding.
    """
    results = {
        'facet_count': facet_count,
        'bytes_per_facet': len(facet_data) / facet_count if facet_count > 0 else 0,
        'theoretical_min_bits': facet_count * 1.62,  # Edgebreaker theoretical minimum
        'theoretical_min_bytes': facet_count * 1.62 / 8,
    }

    # Analyze potential symbol patterns
    # If using variable-length encoding, look for marker bytes

    # Check for potential header
    header_bytes = facet_data[:16]
    results['header_bytes'] = list(header_bytes)

    # Look for byte value 9 as potential marker (seen frequently in sample)
    marker_positions = [i for i, b in enumerate(facet_data) if b == 9]
    results['potential_markers_count'] = len(marker_positions)
    if marker_positions:
        # Calculate average distance between markers
        if len(marker_positions) > 1:
            distances = [marker_positions[i+1] - marker_positions[i]
                        for i in range(len(marker_positions)-1)]
            results['avg_marker_distance'] = sum(distances) / len(distances)

    # Try to decode as nibble pairs
    nibble_counter = Counter()
    for b in facet_data:
        high_nibble = (b >> 4) & 0x0F
        low_nibble = b & 0x0F
        nibble_counter[high_nibble] += 1
        nibble_counter[low_nibble] += 1
    results['nibble_distribution'] = nibble_counter.most_common(16)

    return results


def analyze_vertex_encoding(vertex_data: bytes, expected_vertices: int) -> Dict[str, Any]:
    """
    Analyze vertex data to determine encoding scheme.

    Common vertex encodings:
    - Raw float32 (12 bytes per vertex)
    - Raw float64 (24 bytes per vertex)
    - Quantized integers with scale factor
    - Delta encoding with predictive coding
    """
    results = {
        'total_bytes': len(vertex_data),
        'expected_vertices_12b': len(vertex_data) / 12,
        'expected_vertices_24b': len(vertex_data) / 24,
    }

    # Try different interpretations
    interpretations = []

    # Test 1: Raw float32
    if len(vertex_data) >= 12:
        try:
            sample_f32 = []
            for i in range(min(10, len(vertex_data) // 12)):
                x, y, z = struct.unpack('<fff', vertex_data[i*12:(i+1)*12])
                sample_f32.append((x, y, z))

            # Check if values are reasonable (dental scans typically -100 to 100 mm range)
            reasonable = all(
                -1e6 < v < 1e6
                for xyz in sample_f32
                for v in xyz
            )
            interpretations.append({
                'type': 'float32',
                'sample': sample_f32[:3],
                'reasonable': reasonable
            })
        except struct.error:
            pass

    # Test 2: Check for potential header/metadata
    results['header_32bytes'] = vertex_data[:32].hex()

    # Test 3: Look for repeated patterns (might indicate compression)
    # Check for 4-byte alignment patterns
    if len(vertex_data) >= 100:
        four_byte_chunks = [vertex_data[i:i+4] for i in range(0, min(100, len(vertex_data)), 4)]
        chunk_counter = Counter(four_byte_chunks)
        results['repeated_4byte_chunks'] = len([c for c, count in chunk_counter.items() if count > 1])

    # Test 4: Try to find a bounding box or scale factor in header
    # Often quantized formats store min/max or center + scale
    if len(vertex_data) >= 24:
        potential_bbox = struct.unpack('<ffffff', vertex_data[:24])
        results['potential_bbox_float32'] = potential_bbox

    if len(vertex_data) >= 48:
        potential_bbox_f64 = struct.unpack('<dddddd', vertex_data[:48])
        results['potential_bbox_float64'] = potential_bbox_f64

    results['interpretations'] = interpretations

    return results


def try_decompress(data: bytes) -> Tuple[bool, str, Optional[bytes]]:
    """Try various decompression methods on the data."""
    import zlib
    import gzip
    import bz2
    import lzma

    methods = [
        ('zlib', lambda d: zlib.decompress(d)),
        ('zlib_raw', lambda d: zlib.decompress(d, -15)),
        ('gzip', lambda d: gzip.decompress(d)),
        ('bz2', lambda d: bz2.decompress(d)),
        ('lzma', lambda d: lzma.decompress(d)),
    ]

    for name, decompress_fn in methods:
        try:
            decompressed = decompress_fn(data)
            return True, name, decompressed
        except Exception:
            continue

    return False, 'none', None


def generate_report(analysis: DCMAnalysis, output_dir: Optional[str] = None) -> str:
    """Generate a comprehensive analysis report."""
    lines = []
    lines.append("=" * 70)
    lines.append("DCM FILE ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Basic info
    lines.append("## File Information")
    lines.append(f"  Path: {analysis.file_path}")
    lines.append(f"  Size: {analysis.file_size:,} bytes")
    lines.append(f"  HPS Version: {analysis.hps_version}")
    lines.append(f"  Schema: {analysis.schema}")
    lines.append(f"  CE Version: {analysis.ce_version}")
    lines.append("")

    # Mesh info
    lines.append("## Mesh Information")
    lines.append(f"  Facet Count: {analysis.facet_count:,}")
    lines.append(f"  Facet Color: {analysis.facet_color} (0x{analysis.facet_color:06X})")
    lines.append(f"  Facet Data Size: {analysis.facet_bytes:,} bytes")
    lines.append(f"  Vertex Data Size: {analysis.vertex_bytes:,} bytes")
    lines.append(f"  Bytes per Facet: {analysis.facet_bytes / analysis.facet_count:.2f}")
    lines.append("")

    # Try decompression
    lines.append("## Compression Analysis")

    facet_compressed, facet_method, facet_decompressed = try_decompress(analysis.facet_data)
    vertex_compressed, vertex_method, vertex_decompressed = try_decompress(analysis.vertex_data)

    lines.append(f"  Facet Data: {'Compressed (' + facet_method + ')' if facet_compressed else 'Not standard compression'}")
    if facet_compressed:
        lines.append(f"    Decompressed size: {len(facet_decompressed):,} bytes")

    lines.append(f"  Vertex Data: {'Compressed (' + vertex_method + ')' if vertex_compressed else 'Not standard compression'}")
    if vertex_compressed:
        lines.append(f"    Decompressed size: {len(vertex_decompressed):,} bytes")
    lines.append("")

    # Byte distribution analysis
    lines.append("## Facet Data Analysis")
    facet_dist = analyze_byte_distribution(analysis.facet_data, "Facet Data")
    lines.append(f"  Unique byte values: {facet_dist['unique_values']} / 256")
    lines.append(f"  Entropy: {facet_dist['entropy']:.2f} bits (max 8.0)")
    lines.append(f"  Low-value ratio (0-9): {facet_dist['low_value_ratio']:.1%}")
    lines.append(f"  Most common bytes: {facet_dist['most_common'][:10]}")
    lines.append("")

    # Edgebreaker analysis
    eb_analysis = analyze_edgebreaker_patterns(analysis.facet_data, analysis.facet_count)
    lines.append("## Edgebreaker Pattern Analysis")
    lines.append(f"  Theoretical minimum (Edgebreaker): {eb_analysis['theoretical_min_bytes']:.0f} bytes")
    lines.append(f"  Actual size: {analysis.facet_bytes} bytes")
    lines.append(f"  Efficiency: {eb_analysis['theoretical_min_bytes'] / analysis.facet_bytes:.1%}")
    lines.append(f"  Header bytes: {eb_analysis['header_bytes']}")
    lines.append(f"  Potential marker (0x09) count: {eb_analysis['potential_markers_count']}")
    lines.append("")

    # Vertex analysis
    lines.append("## Vertex Data Analysis")
    vertex_dist = analyze_byte_distribution(analysis.vertex_data, "Vertex Data")
    lines.append(f"  Unique byte values: {vertex_dist['unique_values']} / 256")
    lines.append(f"  Entropy: {vertex_dist['entropy']:.2f} bits (max 8.0)")
    lines.append("")

    vertex_enc = analyze_vertex_encoding(analysis.vertex_data, analysis.facet_count * 3)
    lines.append(f"  If float32: ~{vertex_enc['expected_vertices_12b']:.0f} vertices")
    lines.append(f"  If float64: ~{vertex_enc['expected_vertices_24b']:.0f} vertices")
    lines.append(f"  Header (hex): {vertex_enc['header_32bytes']}")
    lines.append("")

    # Properties
    if analysis.properties:
        lines.append("## Properties")
        for key, value in analysis.properties.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    lines.append("## Signature Hash")
    lines.append(f"  {analysis.signature_hash}")
    lines.append("")

    report = "\n".join(lines)

    # Save outputs if directory specified
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save report
        report_file = output_path / "analysis_report.txt"
        with open(report_file, 'w') as f:
            f.write(report)

        # Save raw binary data for further analysis
        facet_file = output_path / "facet_data.bin"
        with open(facet_file, 'wb') as f:
            f.write(analysis.facet_data)

        vertex_file = output_path / "vertex_data.bin"
        with open(vertex_file, 'wb') as f:
            f.write(analysis.vertex_data)

        # Save analysis as JSON
        json_data = {
            'file_path': analysis.file_path,
            'file_size': analysis.file_size,
            'hps_version': analysis.hps_version,
            'schema': analysis.schema,
            'ce_version': analysis.ce_version,
            'facet_count': analysis.facet_count,
            'facet_color': analysis.facet_color,
            'facet_bytes': analysis.facet_bytes,
            'vertex_bytes': analysis.vertex_bytes,
            'properties': analysis.properties,
            'signature_hash': analysis.signature_hash,
            'facet_distribution': {
                'entropy': facet_dist['entropy'],
                'unique_values': facet_dist['unique_values'],
                'most_common': facet_dist['most_common'][:20],
            },
            'vertex_distribution': {
                'entropy': vertex_dist['entropy'],
                'unique_values': vertex_dist['unique_values'],
            },
            'edgebreaker_analysis': eb_analysis,
        }
        json_file = output_path / "analysis.json"
        with open(json_file, 'w') as f:
            json.dump(json_data, f, indent=2)

        lines.append(f"\nOutput files saved to: {output_dir}")
        lines.append(f"  - analysis_report.txt")
        lines.append(f"  - facet_data.bin")
        lines.append(f"  - vertex_data.bin")
        lines.append(f"  - analysis.json")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Analyze 3Shape DCM file format')
    parser.add_argument('dcm_file', help='Path to DCM file to analyze')
    parser.add_argument('--output-dir', '-o', help='Directory to save analysis outputs')

    args = parser.parse_args()

    if not os.path.exists(args.dcm_file):
        print(f"Error: File not found: {args.dcm_file}")
        sys.exit(1)

    try:
        analysis = parse_dcm_file(args.dcm_file)
        report = generate_report(analysis, args.output_dir)
        print(report)
    except Exception as e:
        print(f"Error analyzing file: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
