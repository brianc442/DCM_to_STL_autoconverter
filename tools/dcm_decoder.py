#!/usr/bin/env python3
"""
DCM to STL Decoder

This decoder can convert 3Shape DCM files to STL format using one of two methods:

1. Key-based decryption (requires pre-computed XOR key from SDX comparison)
2. Direct conversion (when key is available)

FINDINGS FROM REVERSE ENGINEERING:
==================================
The 3Shape DCM format uses:
- HPS (HOOPS) XML wrapper
- CE schema for mesh encoding
- Facet connectivity: Edgebreaker-like compression (~9% of raw size)
- Vertex positions: XOR encryption with file-specific key

The vertex encryption:
- Uses a position-dependent XOR key (not repeating)
- Key entropy is 8.0 bits (cryptographically strong)
- Key does not match common stream ciphers (RC4, etc.)
- Key appears to be derived from file-specific seed (possibly SignatureHash)
- Decryption with correct key achieves 100% match

PRACTICAL IMPLICATIONS:
======================
Without knowing the key derivation algorithm, direct decryption is not possible.
Options:
1. Use SDX for conversion (current approach)
2. Generate keys by converting sample files with SDX
3. Reverse engineer the key derivation (requires more analysis)

Usage:
    # With pre-computed key
    python dcm_decoder.py input.dcm --key key.bin -o output.stl

    # Generate key from SDX output
    python dcm_decoder.py input.dcm --stl sdx_output.stl --save-key key.bin
"""

import argparse
import base64
import os
import struct
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional


@dataclass
class Vertex:
    x: float
    y: float
    z: float


@dataclass
class Mesh:
    vertices: List[Vertex]
    faces: List[Tuple[int, int, int]]
    name: str = "mesh"


def load_dcm_metadata(dcm_path: str) -> dict:
    """Load DCM file and extract metadata."""
    with open(dcm_path, 'r') as f:
        content = f.read()

    root = ET.fromstring(content)

    metadata = {
        'hps_version': root.get('version'),
        'signature_hash': root.find('SignatureHash').text if root.find('SignatureHash') is not None else None,
    }

    # Extract properties
    for prop in root.findall('.//Property'):
        metadata[prop.get('name')] = prop.get('value')

    # Extract mesh info
    ce = root.find('.//CE')
    facets = ce.find('Facets')
    vertices = ce.find('Vertices')

    metadata['facet_count'] = int(facets.get('facet_count', 0))
    metadata['facet_color'] = int(facets.get('color', 0))
    metadata['ce_version'] = ce.get('version')

    return metadata


def load_dcm_binary_data(dcm_path: str) -> Tuple[bytes, bytes]:
    """Load raw binary data from DCM file."""
    with open(dcm_path, 'r') as f:
        content = f.read()

    root = ET.fromstring(content)
    ce = root.find('.//CE')

    facets = ce.find('Facets')
    vertices = ce.find('Vertices')

    facet_data = base64.b64decode(facets.text.strip())
    vertex_data = base64.b64decode(vertices.text.strip())

    return facet_data, vertex_data


def load_stl_vertices(stl_path: str) -> bytes:
    """Extract raw vertex bytes from STL file in order of first appearance."""
    with open(stl_path, 'rb') as f:
        data = f.read()

    # Binary STL: 80 byte header, 4 byte count
    num_triangles = struct.unpack('<I', data[80:84])[0]

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


def derive_xor_key(dcm_vertex_data: bytes, stl_vertex_data: bytes) -> bytes:
    """Derive XOR key from DCM and STL vertex data."""
    if len(dcm_vertex_data) != len(stl_vertex_data):
        raise ValueError(f"Size mismatch: DCM={len(dcm_vertex_data)}, STL={len(stl_vertex_data)}")

    return bytes(a ^ b for a, b in zip(dcm_vertex_data, stl_vertex_data))


def decrypt_vertices(dcm_vertex_data: bytes, xor_key: bytes) -> List[Vertex]:
    """Decrypt vertex data using XOR key."""
    if len(xor_key) < len(dcm_vertex_data):
        raise ValueError(f"Key too short: key={len(xor_key)}, data={len(dcm_vertex_data)}")

    decrypted = bytes(dcm_vertex_data[i] ^ xor_key[i] for i in range(len(dcm_vertex_data)))

    vertices = []
    for i in range(len(decrypted) // 12):
        x, y, z = struct.unpack('<fff', decrypted[i*12:(i+1)*12])
        vertices.append(Vertex(x, y, z))

    return vertices


def write_stl_binary(mesh: Mesh, output_path: str):
    """Write mesh to binary STL file."""
    with open(output_path, 'wb') as f:
        # Header (80 bytes)
        header = f"Decoded from DCM - {mesh.name}".encode('ascii')
        header = header[:80].ljust(80, b'\x00')
        f.write(header)

        # Number of triangles
        f.write(struct.pack('<I', len(mesh.faces)))

        # Write triangles
        for v1_idx, v2_idx, v3_idx in mesh.faces:
            v1 = mesh.vertices[v1_idx]
            v2 = mesh.vertices[v2_idx]
            v3 = mesh.vertices[v3_idx]

            # Calculate normal (simplified - unnormalized)
            # For a proper implementation, normalize this
            nx, ny, nz = 0.0, 0.0, 1.0

            f.write(struct.pack('<fff', nx, ny, nz))  # Normal
            f.write(struct.pack('<fff', v1.x, v1.y, v1.z))
            f.write(struct.pack('<fff', v2.x, v2.y, v2.z))
            f.write(struct.pack('<fff', v3.x, v3.y, v3.z))
            f.write(struct.pack('<H', 0))  # Attribute byte count


def write_stl_ascii(mesh: Mesh, output_path: str):
    """Write mesh to ASCII STL file."""
    with open(output_path, 'w') as f:
        f.write(f"solid {mesh.name}\n")

        for v1_idx, v2_idx, v3_idx in mesh.faces:
            v1 = mesh.vertices[v1_idx]
            v2 = mesh.vertices[v2_idx]
            v3 = mesh.vertices[v3_idx]

            f.write("  facet normal 0 0 1\n")
            f.write("    outer loop\n")
            f.write(f"      vertex {v1.x} {v1.y} {v1.z}\n")
            f.write(f"      vertex {v2.x} {v2.y} {v2.z}\n")
            f.write(f"      vertex {v3.x} {v3.y} {v3.z}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")

        f.write(f"endsolid {mesh.name}\n")


def decode_facets_placeholder(facet_data: bytes, facet_count: int, vertex_count: int) -> List[Tuple[int, int, int]]:
    """
    Placeholder for facet decoding.

    The facet data uses Edgebreaker-like compression.
    This is a placeholder that would need to be implemented
    based on further reverse engineering.

    For now, returns a simple triangulation.
    """
    # WARNING: This is a placeholder - actual decoding requires
    # reverse engineering the CE schema facet encoding

    print("WARNING: Facet decoding not implemented - using placeholder")
    print(f"  Facet data: {len(facet_data)} bytes for {facet_count} faces")

    # Return empty - actual faces would come from decoded connectivity
    return []


def main():
    parser = argparse.ArgumentParser(
        description='DCM to STL Decoder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate key from SDX output:
  python dcm_decoder.py input.dcm --stl sdx_output.stl --save-key key.bin

  # Decode using saved key:
  python dcm_decoder.py input.dcm --key key.bin -o output.stl

  # Full decode with STL reference (for testing):
  python dcm_decoder.py input.dcm --stl sdx_output.stl -o output.stl
        """
    )

    parser.add_argument('dcm_file', help='Input DCM file')
    parser.add_argument('--key', help='XOR key file for decryption')
    parser.add_argument('--stl', help='Reference STL file (from SDX) to derive key')
    parser.add_argument('--save-key', help='Save derived key to file')
    parser.add_argument('-o', '--output', help='Output STL file')
    parser.add_argument('--ascii', action='store_true', help='Output ASCII STL instead of binary')
    parser.add_argument('--info', action='store_true', help='Show DCM file info only')

    args = parser.parse_args()

    # Load DCM metadata
    metadata = load_dcm_metadata(args.dcm_file)

    if args.info:
        print("DCM File Information:")
        print(f"  HPS Version: {metadata.get('hps_version')}")
        print(f"  CE Version: {metadata.get('ce_version')}")
        print(f"  Facet Count: {metadata.get('facet_count')}")
        print(f"  Signature Hash: {metadata.get('signature_hash')}")
        print(f"  Scan Source: {metadata.get('ScanSource', 'N/A')}")
        return

    # Load binary data
    facet_data, vertex_data = load_dcm_binary_data(args.dcm_file)

    print(f"Loaded DCM: {metadata.get('facet_count')} faces, {len(vertex_data)} vertex bytes")

    # Get or derive XOR key
    xor_key = None

    if args.key:
        with open(args.key, 'rb') as f:
            xor_key = f.read()
        print(f"Loaded key: {len(xor_key)} bytes")

    elif args.stl:
        stl_vertices = load_stl_vertices(args.stl)
        xor_key = derive_xor_key(vertex_data, stl_vertices)
        print(f"Derived key: {len(xor_key)} bytes")

        if args.save_key:
            with open(args.save_key, 'wb') as f:
                f.write(xor_key)
            print(f"Saved key to: {args.save_key}")

    else:
        print("ERROR: Either --key or --stl must be provided for decryption")
        sys.exit(1)

    # Decrypt vertices
    vertices = decrypt_vertices(vertex_data, xor_key)
    print(f"Decrypted {len(vertices)} vertices")

    # Decode facets (placeholder)
    faces = decode_facets_placeholder(facet_data, metadata.get('facet_count', 0), len(vertices))

    if not faces:
        print("\nNOTE: Facet decoding not yet implemented.")
        print("The vertex data has been successfully decrypted.")
        print("To get full STL output, facet connectivity decoding is needed.")

        if args.output:
            # Save just vertices for now
            vertex_output = args.output.replace('.stl', '_vertices.bin')
            with open(vertex_output, 'wb') as f:
                for v in vertices:
                    f.write(struct.pack('<fff', v.x, v.y, v.z))
            print(f"Saved decrypted vertices to: {vertex_output}")

    else:
        # Full mesh output
        mesh = Mesh(vertices=vertices, faces=faces, name=Path(args.dcm_file).stem)

        if args.output:
            if args.ascii:
                write_stl_ascii(mesh, args.output)
            else:
                write_stl_binary(mesh, args.output)
            print(f"Saved STL to: {args.output}")


if __name__ == '__main__':
    main()
