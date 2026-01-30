#!/usr/bin/env python3
"""
Batch DCM/STL Pair Analyzer

Processes multiple DCM/STL pairs to extract:
- XOR keys
- File metadata (SignatureHash, properties)
- Facet data patterns
- Statistical correlations

This data can be used to:
1. Discover key derivation algorithm
2. Reverse engineer facet encoding
3. Build predictive models

Usage:
    # Process a directory of pairs (expects matching .dcm and .stl files)
    python batch_pair_analyzer.py /path/to/pairs --output analysis_db.json

    # Process from a CSV mapping file
    python batch_pair_analyzer.py --mapping pairs.csv --output analysis_db.json

    # Analyze existing database
    python batch_pair_analyzer.py --analyze analysis_db.json
"""

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import math
import time


@dataclass
class PairAnalysis:
    """Analysis results for a single DCM/STL pair."""
    dcm_path: str
    stl_path: str

    # DCM metadata
    signature_hash: str
    hps_version: str
    ce_version: str
    ekid: str
    scan_source: str
    source_app: str

    # Mesh stats
    facet_count: int
    vertex_count: int
    facet_bytes: int
    vertex_bytes: int

    # Key analysis
    key_entropy: float
    key_hash_md5: str  # For quick comparison
    key_first_64_hex: str  # First 64 bytes for pattern matching

    # Facet analysis
    facet_entropy: float
    facet_byte_distribution: List[Tuple[int, int]]  # Top 20 byte frequencies
    facet_first_64_hex: str

    # Computed correlations
    key_xor_sighash: str  # Key XOR'd with signature hash pattern

    # Processing info
    process_time: float
    error: Optional[str] = None


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy."""
    if not data:
        return 0
    counter = Counter(data)
    total = len(data)
    return -sum((c/total) * math.log2(c/total) for c in counter.values() if c > 0)


def load_dcm_data(dcm_path: str) -> Tuple[dict, bytes, bytes]:
    """Load DCM metadata and binary data."""
    with open(dcm_path, 'r', encoding='utf-8') as f:
        content = f.read()

    root = ET.fromstring(content)

    # Metadata
    metadata = {
        'signature_hash': '',
        'hps_version': root.get('version', ''),
        'ce_version': '',
        'ekid': '',
        'scan_source': '',
        'source_app': '',
    }

    sig_hash = root.find('SignatureHash')
    if sig_hash is not None and sig_hash.text:
        metadata['signature_hash'] = sig_hash.text.strip()

    # Properties
    for prop in root.findall('.//Property'):
        name = prop.get('name', '')
        value = prop.get('value', '')
        if name == 'EKID':
            metadata['ekid'] = value
        elif name == 'ScanSource':
            metadata['scan_source'] = value
        elif name == 'SourceApp':
            metadata['source_app'] = value

    # CE element
    ce = root.find('.//CE')
    if ce is not None:
        metadata['ce_version'] = ce.get('version', '')

    # Binary data
    facets = root.find('.//Facets')
    vertices = root.find('.//Vertices')

    facet_data = base64.b64decode(facets.text.strip()) if facets is not None and facets.text else b''
    vertex_data = base64.b64decode(vertices.text.strip()) if vertices is not None and vertices.text else b''

    metadata['facet_count'] = int(facets.get('facet_count', 0)) if facets is not None else 0

    return metadata, facet_data, vertex_data


def load_stl_vertices_raw(stl_path: str) -> bytes:
    """Load raw vertex bytes from STL in order of appearance."""
    with open(stl_path, 'rb') as f:
        data = f.read()

    # Check if ASCII or binary
    if data[:5].lower() == b'solid' and b'facet' in data[:1000]:
        return load_stl_vertices_ascii(data)
    else:
        return load_stl_vertices_binary(data)


def load_stl_vertices_binary(data: bytes) -> bytes:
    """Load vertices from binary STL."""
    num_triangles = struct.unpack('<I', data[80:84])[0]

    vertices = []
    vertex_set = set()
    offset = 84

    for _ in range(num_triangles):
        offset += 12  # Skip normal
        for _ in range(3):
            x, y, z = struct.unpack('<fff', data[offset:offset+12])
            vertex_key = (round(x, 6), round(y, 6), round(z, 6))
            if vertex_key not in vertex_set:
                vertex_set.add(vertex_key)
                vertices.append((x, y, z))
            offset += 12
        offset += 2  # Skip attribute

    result = b''
    for x, y, z in vertices:
        result += struct.pack('<fff', x, y, z)

    return result


def load_stl_vertices_ascii(data: bytes) -> bytes:
    """Load vertices from ASCII STL."""
    import re
    content = data.decode('ascii', errors='ignore')

    vertex_pattern = re.compile(r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)', re.IGNORECASE)

    vertices = []
    vertex_set = set()

    for match in vertex_pattern.finditer(content):
        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
        vertex_key = (round(x, 6), round(y, 6), round(z, 6))
        if vertex_key not in vertex_set:
            vertex_set.add(vertex_key)
            vertices.append((x, y, z))

    result = b''
    for x, y, z in vertices:
        result += struct.pack('<fff', x, y, z)

    return result


def analyze_pair(dcm_path: str, stl_path: str) -> PairAnalysis:
    """Analyze a single DCM/STL pair."""
    start_time = time.time()
    error = None

    try:
        # Load data
        metadata, facet_data, dcm_vertex_data = load_dcm_data(dcm_path)
        stl_vertex_data = load_stl_vertices_raw(stl_path)

        # Verify sizes match
        if len(dcm_vertex_data) != len(stl_vertex_data):
            error = f"Size mismatch: DCM={len(dcm_vertex_data)}, STL={len(stl_vertex_data)}"
            # Use minimum length
            min_len = min(len(dcm_vertex_data), len(stl_vertex_data))
            dcm_vertex_data = dcm_vertex_data[:min_len]
            stl_vertex_data = stl_vertex_data[:min_len]

        # Derive XOR key
        xor_key = bytes(a ^ b for a, b in zip(dcm_vertex_data, stl_vertex_data))

        # Key analysis
        key_entropy = calculate_entropy(xor_key)
        key_hash = hashlib.md5(xor_key).hexdigest()
        key_first_64 = xor_key[:64].hex()

        # Facet analysis
        facet_entropy = calculate_entropy(facet_data)
        facet_dist = Counter(facet_data).most_common(20)
        facet_first_64 = facet_data[:64].hex()

        # Key correlation with signature hash
        sig_bytes = bytes.fromhex(metadata['signature_hash']) if metadata['signature_hash'] else b''
        if sig_bytes and len(xor_key) >= len(sig_bytes):
            key_xor_sig = bytes(a ^ b for a, b in zip(xor_key[:len(sig_bytes)], sig_bytes)).hex()
        else:
            key_xor_sig = ''

        process_time = time.time() - start_time

        return PairAnalysis(
            dcm_path=dcm_path,
            stl_path=stl_path,
            signature_hash=metadata['signature_hash'],
            hps_version=metadata['hps_version'],
            ce_version=metadata['ce_version'],
            ekid=metadata['ekid'],
            scan_source=metadata['scan_source'],
            source_app=metadata['source_app'],
            facet_count=metadata['facet_count'],
            vertex_count=len(dcm_vertex_data) // 12,
            facet_bytes=len(facet_data),
            vertex_bytes=len(dcm_vertex_data),
            key_entropy=key_entropy,
            key_hash_md5=key_hash,
            key_first_64_hex=key_first_64,
            facet_entropy=facet_entropy,
            facet_byte_distribution=facet_dist,
            facet_first_64_hex=facet_first_64,
            key_xor_sighash=key_xor_sig,
            process_time=process_time,
            error=error,
        )

    except Exception as e:
        return PairAnalysis(
            dcm_path=dcm_path,
            stl_path=stl_path,
            signature_hash='',
            hps_version='',
            ce_version='',
            ekid='',
            scan_source='',
            source_app='',
            facet_count=0,
            vertex_count=0,
            facet_bytes=0,
            vertex_bytes=0,
            key_entropy=0,
            key_hash_md5='',
            key_first_64_hex='',
            facet_entropy=0,
            facet_byte_distribution=[],
            facet_first_64_hex='',
            key_xor_sighash='',
            process_time=time.time() - start_time,
            error=str(e),
        )


def find_pairs_in_directory(directory: str) -> List[Tuple[str, str]]:
    """Find matching DCM/STL pairs in a directory."""
    pairs = []
    dcm_files = {}

    for root, dirs, files in os.walk(directory):
        for f in files:
            path = os.path.join(root, f)
            if f.lower().endswith('.dcm'):
                base = os.path.splitext(path)[0]
                dcm_files[base] = path

    for base, dcm_path in dcm_files.items():
        stl_path = base + '.stl'
        if os.path.exists(stl_path):
            pairs.append((dcm_path, stl_path))
        else:
            # Try case-insensitive
            stl_path = base + '.STL'
            if os.path.exists(stl_path):
                pairs.append((dcm_path, stl_path))

    return pairs


def process_pairs(pairs: List[Tuple[str, str]], output_path: str, save_keys: bool = False, keys_dir: str = None):
    """Process multiple pairs and save results."""
    results = []
    total = len(pairs)

    print(f"Processing {total} pairs...")

    for i, (dcm_path, stl_path) in enumerate(pairs):
        print(f"  [{i+1}/{total}] {os.path.basename(dcm_path)}", end='', flush=True)

        analysis = analyze_pair(dcm_path, stl_path)
        results.append(asdict(analysis))

        if analysis.error:
            print(f" - ERROR: {analysis.error}")
        else:
            print(f" - OK ({analysis.process_time:.2f}s)")

        # Optionally save keys
        if save_keys and keys_dir and not analysis.error:
            key_path = os.path.join(keys_dir, os.path.basename(dcm_path) + '.key')
            # Regenerate full key
            _, _, dcm_vertex = load_dcm_data(dcm_path)
            stl_vertex = load_stl_vertices_raw(stl_path)
            xor_key = bytes(a ^ b for a, b in zip(dcm_vertex, stl_vertex))
            with open(key_path, 'wb') as f:
                f.write(xor_key)

    # Save results
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved {len(results)} analyses to {output_path}")

    return results


def analyze_database(db_path: str):
    """Analyze patterns in the database."""
    with open(db_path, 'r') as f:
        results = json.load(f)

    print(f"Analyzing {len(results)} pair analyses...")
    print()

    # Filter successful analyses
    successful = [r for r in results if not r.get('error')]
    print(f"Successful: {len(successful)}, Errors: {len(results) - len(successful)}")
    print()

    if not successful:
        print("No successful analyses to examine.")
        return

    # Key patterns
    print("=" * 60)
    print("KEY DERIVATION ANALYSIS")
    print("=" * 60)

    # Check if keys are unique
    key_hashes = [r['key_hash_md5'] for r in successful]
    unique_keys = len(set(key_hashes))
    print(f"Unique keys: {unique_keys} / {len(successful)}")

    if unique_keys < len(successful):
        # Find duplicates
        hash_counts = Counter(key_hashes)
        duplicates = [(h, c) for h, c in hash_counts.items() if c > 1]
        print(f"Duplicate keys found: {len(duplicates)}")
        for h, c in duplicates[:5]:
            matching = [r for r in successful if r['key_hash_md5'] == h]
            print(f"  Hash {h[:16]}... appears {c} times:")
            for m in matching[:3]:
                print(f"    - {m['signature_hash'][:20]}... ({os.path.basename(m['dcm_path'])})")

    # Check key_xor_sighash patterns
    print("\nKey XOR SignatureHash patterns:")
    xor_patterns = Counter(r['key_xor_sighash'][:32] for r in successful if r['key_xor_sighash'])
    for pattern, count in xor_patterns.most_common(10):
        print(f"  {pattern}... : {count} occurrences")

    # Analyze by signature hash
    print("\nSignature hash to key correlation:")
    sig_to_key = defaultdict(list)
    for r in successful:
        sig_to_key[r['signature_hash']].append(r['key_hash_md5'])

    same_sig_different_key = 0
    for sig, keys in sig_to_key.items():
        if len(set(keys)) > 1:
            same_sig_different_key += 1
            print(f"  SigHash {sig[:20]}... has {len(set(keys))} different keys")

    if same_sig_different_key == 0:
        print("  All files with same SignatureHash have same key!")
        print("  THIS SUGGESTS KEY IS DERIVED FROM SIGNATURE HASH")

    # Key first bytes correlation
    print("\nKey first 16 bytes patterns:")
    first_16 = Counter(r['key_first_64_hex'][:32] for r in successful)
    for pattern, count in first_16.most_common(10):
        print(f"  {pattern} : {count}")

    print()
    print("=" * 60)
    print("FACET ENCODING ANALYSIS")
    print("=" * 60)

    # Facet patterns
    print("\nFacet entropy distribution:")
    entropies = [r['facet_entropy'] for r in successful]
    print(f"  Min: {min(entropies):.2f}, Max: {max(entropies):.2f}, Avg: {sum(entropies)/len(entropies):.2f}")

    # Common facet first bytes
    print("\nFacet first 16 bytes patterns:")
    facet_first = Counter(r['facet_first_64_hex'][:32] for r in successful)
    for pattern, count in facet_first.most_common(10):
        print(f"  {pattern} : {count}")

    # Byte distribution analysis
    print("\nFacet byte distributions (aggregated top bytes):")
    all_bytes = Counter()
    for r in successful:
        for byte_val, count in r['facet_byte_distribution']:
            all_bytes[byte_val] += count

    total_bytes = sum(all_bytes.values())
    print(f"  Total facet bytes analyzed: {total_bytes:,}")
    for byte_val, count in all_bytes.most_common(15):
        pct = count / total_bytes * 100
        print(f"  Byte {byte_val:3d} (0x{byte_val:02X}): {pct:.2f}%")

    # Analyze by scan source
    print("\nBreakdown by ScanSource:")
    by_source = defaultdict(list)
    for r in successful:
        by_source[r['scan_source']].append(r)

    for source, items in sorted(by_source.items(), key=lambda x: -len(x[1])):
        avg_entropy = sum(r['key_entropy'] for r in items) / len(items)
        print(f"  {source or 'Unknown'}: {len(items)} files, avg key entropy: {avg_entropy:.4f}")


def main():
    parser = argparse.ArgumentParser(description='Batch DCM/STL pair analyzer')
    parser.add_argument('path', nargs='?', help='Directory with DCM/STL pairs or analysis DB')
    parser.add_argument('--mapping', help='CSV file mapping DCM to STL paths')
    parser.add_argument('--output', '-o', default='pair_analysis.json', help='Output JSON database')
    parser.add_argument('--analyze', action='store_true', help='Analyze existing database')
    parser.add_argument('--save-keys', action='store_true', help='Save extracted keys')
    parser.add_argument('--keys-dir', default='extracted_keys', help='Directory for saved keys')
    parser.add_argument('--limit', type=int, help='Limit number of pairs to process')

    args = parser.parse_args()

    if args.analyze:
        if not args.path:
            print("Please specify database path with --analyze")
            sys.exit(1)
        analyze_database(args.path)
        return

    pairs = []

    if args.mapping:
        # Load from CSV
        import csv
        with open(args.mapping, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    pairs.append((row[0], row[1]))
    elif args.path:
        pairs = find_pairs_in_directory(args.path)
    else:
        print("Please specify a directory or --mapping file")
        sys.exit(1)

    if not pairs:
        print("No pairs found!")
        sys.exit(1)

    if args.limit:
        pairs = pairs[:args.limit]

    if args.save_keys:
        os.makedirs(args.keys_dir, exist_ok=True)

    process_pairs(pairs, args.output, args.save_keys, args.keys_dir)

    # Auto-analyze if we have results
    print("\n" + "=" * 60)
    analyze_database(args.output)


if __name__ == '__main__':
    main()
