#!/usr/bin/env python3
"""
SDX Test Harness

This script creates a test framework for comparing SDX output with our
decoding attempts. It can:
1. Run SDX to convert DCM to STL
2. Parse the resulting STL file
3. Compare against our decoded mesh data
4. Help identify patterns for reverse engineering

For Windows: Run directly
For Linux: Use this to analyze STL files created by SDX on Windows

Usage:
    python sdx_test_harness.py <dcm_file> --stl <existing_stl>
    python sdx_test_harness.py <dcm_file> --convert  # Windows only
"""

import argparse
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import json


@dataclass
class Vertex:
    x: float
    y: float
    z: float

    def __eq__(self, other):
        if not isinstance(other, Vertex):
            return False
        # Use tolerance for floating point comparison
        return (abs(self.x - other.x) < 1e-6 and
                abs(self.y - other.y) < 1e-6 and
                abs(self.z - other.z) < 1e-6)

    def __hash__(self):
        # Round for hashing
        return hash((round(self.x, 4), round(self.y, 4), round(self.z, 4)))


@dataclass
class Face:
    v1: int
    v2: int
    v3: int
    normal: Optional[Tuple[float, float, float]] = None


@dataclass
class STLMesh:
    """Parsed STL mesh data."""
    vertices: List[Vertex]
    faces: List[Face]
    vertex_map: dict  # Maps vertex to index
    is_binary: bool
    name: str


def parse_stl_ascii(content: str) -> STLMesh:
    """Parse ASCII STL file."""
    vertices = []
    faces = []
    vertex_map = {}
    name = ""

    # Extract solid name
    solid_match = re.search(r'solid\s+(\S*)', content)
    if solid_match:
        name = solid_match.group(1)

    # Parse facets
    facet_pattern = re.compile(
        r'facet\s+normal\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'outer\s+loop\s*'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*'
        r'endloop\s*'
        r'endfacet',
        re.IGNORECASE | re.MULTILINE
    )

    for match in facet_pattern.finditer(content):
        nx, ny, nz = float(match.group(1)), float(match.group(2)), float(match.group(3))
        v1 = Vertex(float(match.group(4)), float(match.group(5)), float(match.group(6)))
        v2 = Vertex(float(match.group(7)), float(match.group(8)), float(match.group(9)))
        v3 = Vertex(float(match.group(10)), float(match.group(11)), float(match.group(12)))

        # Get or create vertex indices
        face_indices = []
        for v in [v1, v2, v3]:
            if v not in vertex_map:
                vertex_map[v] = len(vertices)
                vertices.append(v)
            face_indices.append(vertex_map[v])

        faces.append(Face(face_indices[0], face_indices[1], face_indices[2],
                         normal=(nx, ny, nz)))

    return STLMesh(vertices, faces, vertex_map, is_binary=False, name=name)


def parse_stl_binary(data: bytes) -> STLMesh:
    """Parse binary STL file."""
    vertices = []
    faces = []
    vertex_map = {}

    # Header: 80 bytes
    header = data[:80]
    name = header.decode('ascii', errors='ignore').strip('\x00')

    # Number of triangles: 4 bytes (uint32)
    num_triangles = struct.unpack('<I', data[80:84])[0]

    offset = 84
    for _ in range(num_triangles):
        # Normal: 3 x float32
        nx, ny, nz = struct.unpack('<fff', data[offset:offset+12])
        offset += 12

        # 3 vertices: each 3 x float32
        face_indices = []
        for _ in range(3):
            x, y, z = struct.unpack('<fff', data[offset:offset+12])
            offset += 12
            v = Vertex(x, y, z)
            if v not in vertex_map:
                vertex_map[v] = len(vertices)
                vertices.append(v)
            face_indices.append(vertex_map[v])

        # Attribute byte count: 2 bytes (usually 0)
        offset += 2

        faces.append(Face(face_indices[0], face_indices[1], face_indices[2],
                         normal=(nx, ny, nz)))

    return STLMesh(vertices, faces, vertex_map, is_binary=True, name=name)


def load_stl(file_path: str) -> STLMesh:
    """Load and parse an STL file (auto-detect binary vs ASCII)."""
    with open(file_path, 'rb') as f:
        data = f.read()

    # Check if binary or ASCII
    # Binary STL has 80-byte header, then uint32 triangle count
    # ASCII STL starts with "solid"
    if data[:5].lower() == b'solid':
        # Might be ASCII, but could also be binary with "solid" in header
        # Check if there's "facet" after the header
        if b'facet' in data[:1000]:
            return parse_stl_ascii(data.decode('ascii', errors='ignore'))

    # Assume binary
    return parse_stl_binary(data)


def analyze_mesh(mesh: STLMesh) -> dict:
    """Analyze mesh properties."""
    # Bounding box
    xs = [v.x for v in mesh.vertices]
    ys = [v.y for v in mesh.vertices]
    zs = [v.z for v in mesh.vertices]

    bbox = {
        'min': (min(xs), min(ys), min(zs)),
        'max': (max(xs), max(ys), max(zs)),
        'center': ((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2),
        'size': (max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs))
    }

    # Vertex statistics
    vertex_coords = []
    for v in mesh.vertices:
        vertex_coords.extend([v.x, v.y, v.z])

    coord_min = min(vertex_coords)
    coord_max = max(vertex_coords)

    # Check if coordinates might be quantized
    # Look for common denominators or regular spacing
    unique_x = sorted(set(v.x for v in mesh.vertices))
    unique_y = sorted(set(v.y for v in mesh.vertices))
    unique_z = sorted(set(v.z for v in mesh.vertices))

    return {
        'vertex_count': len(mesh.vertices),
        'face_count': len(mesh.faces),
        'is_binary': mesh.is_binary,
        'name': mesh.name,
        'bbox': bbox,
        'coord_range': (coord_min, coord_max),
        'unique_x_count': len(unique_x),
        'unique_y_count': len(unique_y),
        'unique_z_count': len(unique_z),
        'bytes_per_vertex_uncompressed': 12,  # 3 x float32
        'total_vertex_bytes': len(mesh.vertices) * 12,
    }


def export_vertex_data(mesh: STLMesh, output_path: str):
    """Export vertex data for comparison with DCM decoding."""
    with open(output_path, 'wb') as f:
        for v in mesh.vertices:
            f.write(struct.pack('<fff', v.x, v.y, v.z))

    print(f"Exported {len(mesh.vertices)} vertices to {output_path}")


def export_face_data(mesh: STLMesh, output_path: str):
    """Export face indices for comparison."""
    with open(output_path, 'wb') as f:
        for face in mesh.faces:
            f.write(struct.pack('<III', face.v1, face.v2, face.v3))

    print(f"Exported {len(mesh.faces)} faces to {output_path}")


def compare_with_dcm(mesh: STLMesh, dcm_vertex_data: bytes, dcm_facet_data: bytes):
    """Compare STL mesh with DCM raw data."""
    print("\n## STL vs DCM Comparison")
    print(f"STL vertices: {len(mesh.vertices)}")
    print(f"STL faces: {len(mesh.faces)}")
    print(f"DCM vertex bytes: {len(dcm_vertex_data)}")
    print(f"DCM facet bytes: {len(dcm_facet_data)}")

    # Calculate expected sizes
    stl_vertex_bytes = len(mesh.vertices) * 12  # float32 x 3
    print(f"\nSTL vertex data size: {stl_vertex_bytes} bytes")
    print(f"DCM vertex data size: {len(dcm_vertex_data)} bytes")
    print(f"Compression ratio: {len(dcm_vertex_data) / stl_vertex_bytes:.2%}")

    stl_face_bytes = len(mesh.faces) * 12  # uint32 x 3
    print(f"\nSTL face index size: {stl_face_bytes} bytes")
    print(f"DCM facet data size: {len(dcm_facet_data)} bytes")
    print(f"Compression ratio: {len(dcm_facet_data) / stl_face_bytes:.2%}")

    # Try to find STL vertex bytes in DCM data
    print("\n## Searching for STL vertex patterns in DCM data...")
    stl_raw = struct.pack('<fff', mesh.vertices[0].x, mesh.vertices[0].y, mesh.vertices[0].z)
    if stl_raw in dcm_vertex_data:
        pos = dcm_vertex_data.find(stl_raw)
        print(f"Found first vertex at offset {pos}!")
    else:
        print("First STL vertex not found directly in DCM data")
        print("This suggests the DCM uses different encoding (quantized, delta, encrypted)")

    # Check if DCM might store vertices in different order
    # by looking for any STL vertex
    found_any = False
    for i, v in enumerate(mesh.vertices[:100]):  # Check first 100
        raw = struct.pack('<fff', v.x, v.y, v.z)
        if raw in dcm_vertex_data:
            pos = dcm_vertex_data.find(raw)
            print(f"Found vertex {i} at offset {pos}")
            found_any = True
            break

    if not found_any:
        print("No raw float32 vertices found in DCM data")
        print("The vertex data is definitely encoded/encrypted")


def main():
    parser = argparse.ArgumentParser(description='SDX Test Harness')
    parser.add_argument('dcm_file', nargs='?', help='Path to DCM file')
    parser.add_argument('--stl', help='Path to existing STL file (converted by SDX)')
    parser.add_argument('--convert', action='store_true',
                       help='Convert using SDX (Windows only)')
    parser.add_argument('--output-dir', '-o', help='Output directory for exported data')
    parser.add_argument('--compare', action='store_true',
                       help='Compare STL with DCM data')

    args = parser.parse_args()

    if not args.stl and not args.convert:
        print("Please specify either --stl <file> or --convert")
        sys.exit(1)

    stl_path = args.stl

    # Load and analyze STL
    if stl_path and os.path.exists(stl_path):
        print(f"Loading STL: {stl_path}")
        mesh = load_stl(stl_path)

        analysis = analyze_mesh(mesh)
        print("\n## Mesh Analysis")
        for key, value in analysis.items():
            print(f"  {key}: {value}")

        # Export data for comparison
        if args.output_dir:
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            export_vertex_data(mesh, str(output_dir / "stl_vertices.bin"))
            export_face_data(mesh, str(output_dir / "stl_faces.bin"))

            # Save analysis as JSON
            with open(output_dir / "stl_analysis.json", 'w') as f:
                # Convert non-serializable values
                analysis_json = {k: (list(v) if isinstance(v, tuple) else v)
                                for k, v in analysis.items()}
                if 'bbox' in analysis_json:
                    analysis_json['bbox'] = {
                        k: list(v) for k, v in analysis['bbox'].items()
                    }
                json.dump(analysis_json, f, indent=2)

        # Compare with DCM if requested
        if args.compare and args.dcm_file and os.path.exists(args.dcm_file):
            import base64
            import xml.etree.ElementTree as ET

            with open(args.dcm_file, 'r') as f:
                content = f.read()

            root = ET.fromstring(content)
            ce = root.find('.//CE')
            facets = ce.find('Facets')
            vertices = ce.find('Vertices')

            dcm_vertex_data = base64.b64decode(vertices.text.strip())
            dcm_facet_data = base64.b64decode(facets.text.strip())

            compare_with_dcm(mesh, dcm_vertex_data, dcm_facet_data)

            # Print vertex bounding box to help with decoding
            print("\n## STL Vertex Bounds (for decoding reference)")
            print(f"  X: {analysis['bbox']['min'][0]:.6f} to {analysis['bbox']['max'][0]:.6f}")
            print(f"  Y: {analysis['bbox']['min'][1]:.6f} to {analysis['bbox']['max'][1]:.6f}")
            print(f"  Z: {analysis['bbox']['min'][2]:.6f} to {analysis['bbox']['max'][2]:.6f}")

            # Print first few vertices
            print("\n## First 10 STL Vertices")
            for i, v in enumerate(mesh.vertices[:10]):
                print(f"  {i}: ({v.x:.6f}, {v.y:.6f}, {v.z:.6f})")

    elif args.convert:
        print("SDX conversion requires Windows with SDX installed")
        print("This functionality would use the existing SDX COM interface")

        # Check if running on Windows
        if sys.platform != 'win32':
            print("ERROR: SDX conversion only available on Windows")
            sys.exit(1)

        # Would use the existing code to convert
        print("TODO: Implement SDX conversion wrapper")

    else:
        print(f"STL file not found: {stl_path}")
        sys.exit(1)


if __name__ == '__main__':
    main()
