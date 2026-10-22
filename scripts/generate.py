#!/usr/bin/env python3
"""Generate Crystal CrImage constants from an upstream icon ZIP."""

import argparse
import base64
import ctypes as c
from ctypes.util import find_library
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

SOURCE_REPO = "primer/octicons"
PACKAGE = "octicons"
MODULE = "Octicons"


def bind(library, name, result, *args):
    function = getattr(c.CDLL(find_library(library) or library), name)
    function.restype, function.argtypes = result, args
    return function


ptr, integer = c.c_void_p, c.c_int
new_handle = bind("rsvg-2", "rsvg_handle_new_from_data", ptr, c.c_char_p, c.c_size_t, ptr)
render_document = bind("rsvg-2", "rsvg_handle_render_document", integer, ptr, ptr, ptr, ptr)
new_surface = bind("cairo", "cairo_image_surface_create", ptr, integer, integer, integer)
new_context = bind("cairo", "cairo_create", ptr, ptr)
write_png_stream = bind("cairo", "cairo_surface_write_to_png_stream", integer, ptr, ptr, ptr)
destroy_context = bind("cairo", "cairo_destroy", None, ptr)
destroy_surface = bind("cairo", "cairo_surface_destroy", None, ptr)
unref = bind("gobject-2.0", "g_object_unref", None, ptr)


class Rectangle(c.Structure):
    _fields_ = [(field, c.c_double) for field in ("x", "y", "width", "height")]


WRITE_CALLBACK = c.CFUNCTYPE(integer, ptr, ptr, c.c_uint)


def rasterize(svg, path, width, height):
    handle = new_handle(svg, len(svg), None)
    if not handle:
        raise ValueError(f"Cannot parse SVG: {path}")
    surface = new_surface(0, width, height)
    context = new_context(surface)
    png = bytearray()

    @WRITE_CALLBACK
    def collect(_closure, data, length):
        png.extend(c.string_at(data, length))
        return 0

    try:
        viewport = Rectangle(0, 0, width, height)
        if not render_document(handle, context, c.byref(viewport), None):
            raise ValueError(f"Cannot render SVG: {path}")
        if write_png_stream(surface, collect, None):
            raise ValueError(f"Cannot encode PNG: {path}")
        result = bytes(png)
        if result[:8] != b"\x89PNG\r\n\x1a\n" or result[16:24] != width.to_bytes(4, "big") + height.to_bytes(4, "big"):
            raise ValueError(f"Invalid PNG dimensions: {path}")
        return result
    finally:
        destroy_context(context)
        destroy_surface(surface)
        unref(handle)


def pascal(name):
    return "".join(part.capitalize() for part in name.split("-"))


def icon_entries(archive):
    entries = []
    seen = {}
    root = rf"[^/]+/{'icons' if PACKAGE == 'octicons' else 'package/icons/(?:fill|outline)/svg' if PACKAGE == 'eva' else 'src/svg'}/"
    pattern = re.compile(root + r"([a-z0-9-]+)\.svg\Z")
    with zipfile.ZipFile(archive) as source:
        for path in source.namelist():
            match = pattern.fullmatch(path)
            if not match:
                continue
            name = match[1]
            svg = source.read(path)
            attributes = ET.fromstring(svg).attrib
            if PACKAGE == "octicons":
                width, height = int(attributes["width"]), int(attributes["height"])
                size = int(name.rsplit("-", 1)[-1])
                key = str(size)
                identifier = pascal(name)
            elif PACKAGE == "eva":
                width = height = 24
                style = "filled" if "/fill/" in path else "outline"
                key = f"24_{style}"
                base = name.removesuffix("-outline") if style == "outline" else name
                identifier = pascal(base) + "24" + pascal(style)
            else:
                if name.startswith("logo-"):
                    style, base = "logos", name
                elif name.endswith("-outline"):
                    style, base = "outline", name[:-8]
                elif name.endswith("-sharp"):
                    style, base = "sharp", name[:-6]
                else:
                    style, base = "filled", name
                for size in (24, 32):
                    identifier = pascal(base) + str(size) + ("" if style == "logos" else pascal(style))
                    add_entry(entries, seen, f"{size}_{style}", identifier, path, svg, size, size)
                continue
            add_entry(entries, seen, key, identifier, path, svg, width, height)
    if not entries:
        raise ValueError("No icons found in source archive")
    return sorted(entries)


def add_entry(entries, seen, key, identifier, path, svg, width, height):
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", identifier):
        raise ValueError(f"Invalid Crystal identifier: {identifier} ({path})")
    if identifier in seen:
        raise ValueError(f"Conflicting Crystal identifier: {identifier}: {seen[identifier]}, {path}")
    seen[identifier] = path
    entries.append((key, identifier, path, svg, width, height))


def generate(archive, output_dir, check=False):
    entries = icon_entries(archive)
    header = f"# Generated from {SOURCE_REPO} (MIT). Do not edit manually.\n"
    common = (header + 'require "base64"\nrequire "crimage"\n\n'
              f'module Icon\n  module {MODULE}\n'
              '    # Shared CrImage images. Copy before modifying.\n'
              '    private def self.decode_png(encoded : String)\n'
              '      CrImage.read(IO::Memory.new(Base64.decode(encoded)))\n'
              '    end\n  end\nend\n')
    files = {"common.cr": common}
    groups = {}
    for key, identifier, path, svg, width, height in entries:
        png = rasterize(svg, path, width, height)
        groups.setdefault(key, []).append((identifier, path, width, height, base64.b64encode(png).decode()))
    for key, icons in sorted(groups.items()):
        lines = [header.rstrip(), 'require "./common"', '', 'module Icon', f'  module {MODULE}']
        for identifier, path, width, height, encoded in icons:
            lines += [f'    # {path.split("/", 1)[-1]} ({width}x{height})',
                      f'    {identifier} = decode_png("{encoded}")']
        files[f"{key}.cr"] = "\n".join(lines + ['  end', 'end', ''])
        print(f"Rendered {key}: {len(icons)} icons", flush=True)
    files[f"icon-{PACKAGE}.cr"] = header + "".join(f'require "./{key}"\n' for key in sorted(groups))
    stale = {p.name for p in output_dir.glob("[0-9]*.cr") if p.name not in files}
    stale |= {p.name for p in output_dir.glob("*.cr") if p.name not in files}
    if check:
        mismatched = [name for name, content in files.items()
                      if not (output_dir / name).is_file() or (output_dir / name).read_text() != content]
        if mismatched or stale:
            raise ValueError(f"Generated files differ: {mismatched}; stale files: {sorted(stale)}")
        print(f"OK: {len(entries)} images, generated files match")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in stale:
            (output_dir / name).unlink()
        for name, content in files.items():
            (output_dir / name).write_text(content)
        print(f"Generated {len(entries)} images in {len(files)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help=f"Source ZIP from https://github.com/{SOURCE_REPO}")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "src")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generate(args.archive, args.output_dir, args.check)
