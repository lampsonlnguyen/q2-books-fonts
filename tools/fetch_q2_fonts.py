#!/usr/bin/env python3
"""Fetch pinned CrossPoint SD fonts for the Q2 reader, with exact SHA-256 verification.

Uses the original CrossPoint project's pinned 12pt cpfont v4 release.
Smaller 8–11pt packs are built by build_q2_small_font_assets.py.
Never changes
firmware/system fonts or embeds a different Q2-native rendering engine.
"""
from __future__ import annotations
import hashlib
import pathlib
import sys
import urllib.request
from crosspoint_script_fonts import RELEASE as SCRIPT_RELEASE, SCRIPT_FONTS

RELEASE = "https://github.com/crosspoint-reader/crosspoint-fonts/releases/download/sd-fonts-m1-b4"
SHA256 = {
    "NotoSansExtended_12.cpfont": "17e2dd57a2507203dcb04e1ce4f7f49c755cd327550c8c8333ac713655b06bd1",
    "NotoSerifExtended_12.cpfont": "90cbcf43bc504f1ca3dad068e9286d7818dec6522fa2c9810b0e421637944091",
}
# Original upstream CrossPoint CJK-JP bitmap font: shared Han ideographs,
# Japanese kana and common punctuation. The upstream release currently does
# not ship a locale-specific SC glyph pack; this fallback restores legibility
# for common Simplified Chinese, but Japanese regional glyph forms may differ.
CJK_RELEASE = "https://github.com/crosspoint-reader/crosspoint-fonts/releases/download/sd-fonts-m1-b4-r13"
CJK_SHA256 = {
    12: ("08089c8cd141e38c8a6bbe672215a40da4847c524f097e5200ee89eafcdd80d0", 7714459),
}



def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fetch_q2_fonts.py OUTPUT_DIRECTORY", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for original, expected in SHA256.items():
        family, size = original.split("_")
        short = "sans" if family == "NotoSansExtended" else "serif"
        dest = out / f"{short}-{size}"
        with urllib.request.urlopen(f"{RELEASE}/{original}", timeout=90) as response:
            data = response.read(4_000_000)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected:
            raise RuntimeError(f"{original}: expected {expected}, got {digest}")
        if len(data) < 200_000:
            raise RuntimeError(f"{original}: implausibly short font")
        dest.with_suffix(".cpfont").write_bytes(data)
        print(f"Verified {original}: {len(data)} bytes")
    # A single CJK face per size is shared by both UI typography families.
    # Keep source hashes fixed: packaging a truncated/changed font must fail.
    for size, (expected, expected_size) in CJK_SHA256.items():
        name = f"NotoSansCJKJP_{size}.cpfont"
        dest = out / f"cjk-{size}.cpfont"
        with urllib.request.urlopen(f"{CJK_RELEASE}/{name}", timeout=120) as response:
            data = response.read(17_000_000)
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected or len(data) != expected_size:
            raise RuntimeError(f"{name}: digest/size mismatch: {digest}, {len(data)}")
        dest.write_bytes(data)
        print(f"Verified {name}: {len(data)} bytes")
    # All script families published by the upstream CrossPoint release:
    # Hangul, Devanagari, Bengali, Gujarati, Gurmukhi, Kannada,
    # Malayalam, Odia, Sinhala, Tamil, Telugu, Arabic and Hebrew.
    # Disk-resident .cpfont files: only coverage intervals/needed glyphs
    # are loaded by the Q2 reader, not the full pixel data for all fonts.
    for slug, (family, description, sizes) in SCRIPT_FONTS.items():
        for point_size in (12,):
            expected, expected_size = sizes[str(point_size)]
            source = f"{SCRIPT_RELEASE}/{family}_{point_size}.cpfont"
            dest = out / f"{slug}-{point_size}.cpfont"
            with urllib.request.urlopen(source, timeout=120) as response:
                data = response.read(expected_size + 1)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected or len(data) != expected_size:
                raise RuntimeError(
                    f"{family}_{point_size}: digest/size mismatch {digest} ({len(data)})")
            dest.write_bytes(data)
            print(f"Verified {slug} {point_size}pt ({description}): {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
