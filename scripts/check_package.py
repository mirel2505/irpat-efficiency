"""Check the tracked installable package and build a private validation ZIP."""
from pathlib import Path, PurePosixPath
import ast
import json
import struct
import subprocess
import tempfile
import zipfile
import zlib

DOMAIN = "irpat_efficiency"
PREFIX = f"custom_components/{DOMAIN}/"
BRAND = {"brand/icon.png": 256, "brand/icon@2x.png": 512}


def verify_png(data, expected_size):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature"
    cursor = 8
    dimensions = None
    pixels = []
    ended = False
    while cursor < len(data):
        size = struct.unpack_from(">I", data, cursor)[0]
        kind = data[cursor+4:cursor+8]
        end = cursor+8+size
        assert end+4 <= len(data), "Truncated PNG chunk"
        chunk = data[cursor+8:end]
        assert zlib.crc32(kind+chunk) == struct.unpack_from(">I", data, end)[0], "PNG CRC mismatch"
        if kind == b"IHDR":
            dimensions = struct.unpack_from(">II", chunk)
        elif kind == b"IDAT":
            pixels.append(chunk)
        elif kind == b"IEND":
            ended = True
            assert end+4 == len(data), "Trailing PNG data"
        cursor = end+4
    assert ended and dimensions == (expected_size, expected_size), "Invalid icon dimensions"
    assert pixels and zlib.decompress(b"".join(pixels)), "Invalid PNG pixel data"


def verify_archive(archive):
    names = set(archive.namelist())
    for path in ("manifest.json", "__init__.py", "config_flow.py", "options_flow.py",
                 "backup.py", "frontend/panel.js", "strings.json",
                 "translations/en.json", "translations/ro.json", *BRAND):
        assert PREFIX+path in names, f"Missing package file: {path}"
    for path in ("hacs.json", "README.md", "LICENSE"):
        assert path in names, f"Missing repository file: {path}"
    assert archive.testzip() is None, "Archive CRC failure"
    manifest = json.loads(archive.read(PREFIX+"manifest.json"))
    metadata = json.loads(archive.read("hacs.json"))
    assert manifest["domain"] == DOMAIN and manifest["config_flow"] is True
    assert manifest["name"] == metadata["name"] and manifest["version"]
    assert not metadata.get("content_in_root") and not metadata.get("zip_release")
    for path in ("strings.json", "translations/en.json", "translations/ro.json"):
        assert isinstance(json.loads(archive.read(PREFIX+path)), dict)
    for path, size in BRAND.items():
        verify_png(archive.read(PREFIX+path), size)
    modules = {PurePosixPath(p).stem for p in names
               if p.startswith(PREFIX) and p.endswith(".py")}
    for p in names:
        assert not any(part in ("__pycache__", ".storage", ".git") for part in PurePosixPath(p).parts)
        if p.startswith(PREFIX) and p.endswith(".py"):
            source = archive.read(p)
            tree = ast.parse(source, filename=p)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                    assert node.module.split(".")[0] in modules, f"Missing relative import in {p}: {node.module}"
    return len([p for p in names if p.startswith(PREFIX) and not p.endswith("/")]), manifest["version"]


def main():
    # Archive from HEAD only, never from a live Home Assistant directory.
    with tempfile.TemporaryDirectory() as temp:
        destination = Path(temp)/"irpat-validation.zip"
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "archive", "--format=zip", f"--output={destination}",
                        sha, PREFIX.rstrip("/"), "hacs.json", "README.md", "LICENSE"],
                       check=True)
        with zipfile.ZipFile(destination) as archive:
            files, version = verify_archive(archive)
        print(f"Package validation passed: {files} integration files; version {version}; commit {sha}")


if __name__ == "__main__":
    main()
