#!/usr/bin/env python3
"""Generate real CrossPoint CPFONT v4 glyphs at 8–14 pt for Shanling Q2.

The 12 pt assets remain pinned to official CrossPoint release SHA-256 hashes
in fetch_q2_fonts.py. Smaller fonts must be *rasterized at their real point
sizes* with correct metrics; scaling existing 12 pt bitmaps corrupts shaping
and page layout. Source uses a pinned CrossPoint repository commit and its own
font converter, including its license files.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

import yaml
from crosspoint_script_fonts import SCRIPT_FONTS

# Pinned upstream snapshot. Only the font build tooling and source-family
# definitions are used; no ESP32 firmware is compiled for the Q2.
CROSSPOINT_REF = "42d58daaabcf469a2e5e1ba871714fb9dcf51d29"
CROSSPOINT_URL = "https://github.com/crosspoint-reader/crosspoint-reader.git"
SIZES = (8, 9, 10, 11, 13, 14)
ALL_SIZES = tuple(range(8, 15))
# CrossInk's named reader font catalog. The extra families are generated at
# all three 10/11/12pt sizes; the original two and script fallbacks reuse the
# officially SHA-pinned 12pt CrossPoint releases.
CROSSINK_REF = "9914146eeae7b46b300f475a16c32426fc02ec1f"
CROSSINK_URL = "https://github.com/uxjulia/CrossInk.git"
CROSSINK_FAMILIES = {
    "Bitter": "bitter",
    "Lexend Deca": "lexenddeca",
    "ChareInk": "chareink",
    "Literata": "literata",
    "Merriweather": "merriweather",
    "Inter": "inter",
    "AtkinsonHyperlegibleNext": "atkinson",
}
FAMILIES = {
    "NotoSansExtended": "sans",
    "NotoSerifExtended": "serif",
    "NotoSansCJKJP": "cjk",
    **{font: slug for slug, (font, _desc, _assets) in SCRIPT_FONTS.items()},
    **CROSSINK_FAMILIES,
}
INDIC_RANGES = {
    "devanagari": "(0x0900-0x097F)",
    "bengali": "(0x0980-0x09FF)",
    "gurmukhi": "(0x0A00-0x0A7F)",
    "gujarati": "(0x0A80-0x0AFF)",
    "oriya": "(0x0B00-0x0B7F)",
    "tamil": "(0x0B80-0x0BFF)",
    "telugu": "(0x0C00-0x0C7F)",
    "kannada": "(0x0C80-0x0CFF)",
    "malayalam": "(0x0D00-0x0D7F)",
    "sinhala": "(0x0D80-0x0DFF)",
}


def run(*args: str) -> None:
    subprocess.run(list(args), check=True)


def write_license_bundle(out: pathlib.Path, upstream: pathlib.Path,
                         crossink: pathlib.Path, catalog: dict) -> None:
    """One text file with, per generated family, its source and license, then
    every license text found in the pinned repositories and the CI host's
    Noto packages. (build-sd-fonts.py writes no LICENSE of its own.)"""
    lines = ["Fonts generated for Books (Shanling Q2) from these sources.",
             "Every family listed is under the SIL Open Font License 1.1",
             "unless its own license text below says otherwise.", ""]
    for name in FAMILIES:
        style = catalog[name]["styles"]["regular"]
        source = style.get("url") or style.get("path") or "?"
        lines.append(f"- {name}: {source}")
    texts = []
    for root in (upstream, crossink):
        texts.append(root / "LICENSE")
        for pattern in ("lib/EpdFont/**/OFL*.txt", "lib/EpdFont/**/*-OFL.txt",
                        "lib/EpdFont/**/UFL.txt", "lib/EpdFont/scalableFonts/licenses/*.txt"):
            texts.extend(sorted(root.glob(pattern)))
    texts += [pathlib.Path("/usr/share/doc/fonts-noto-core/copyright"),
              pathlib.Path("/usr/share/doc/fonts-noto-cjk/copyright")]
    seen = set()
    for path in texts:
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        lines += ["", "=" * 72, f"{path.name} ({path.parent.name})", "=" * 72,
                  path.read_text(errors="replace")]
    if not any(p.name.upper().startswith("OFL") or "-OFL" in p.name for p in seen):
        raise RuntimeError("No SIL OFL text found for the font license bundle")
    out.write_text("\n".join(lines) + "\n")


# Smooth book text (reader/SmoothGlyphs.hpp) draws the reading families'
# glyphs from their TrueType sources at full coverage, over CrossPoint's own
# layout. The files ship unmodified (no subsetting: the OFL counts a subset
# as a modified font), named <slug>-<style>.ttf.
# Bitter is left out: its variable source does not draw where its .cpfont does
# (the device build measured a 2-3 px vertical shift), so it keeps CrossPoint's
# 2-bit glyphs until the matching source is found.
READING_SLUGS = {"NotoSansExtended": "sans", "NotoSerifExtended": "serif",
                 **{name: slug for name, slug in CROSSINK_FAMILIES.items() if slug != "bitter"}}


def _style_key(name: str) -> str:
    n = name.lower().replace("_", "").replace("-", "")
    bold, italic = "bold" in n, "italic" in n or "oblique" in n
    return "bolditalic" if bold and italic else "bold" if bold else "italic" if italic else "regular"


def _style_source(entry, roots, cache: pathlib.Path):
    """A style's source file: a path (absolute, or under one of the roots)
    or a URL (downloaded once). Lists take their first item."""
    if isinstance(entry, list):
        entry = entry[0] if entry else {}
    if isinstance(entry, str):
        entry = {"path": entry}
    path = entry.get("path") if isinstance(entry, dict) else None
    url = entry.get("url") if isinstance(entry, dict) else None
    if path:
        for candidate in [pathlib.Path(path)] + [root / path for root in roots]:
            if candidate.is_file():
                return candidate
    if url:
        import urllib.parse
        import urllib.request
        dest = cache / pathlib.Path(urllib.parse.urlparse(url).path).name
        if not dest.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=120) as response:
                dest.write_bytes(response.read())
        return dest
    return None


_NOTO_FILES = {"NotoSansExtended": "NotoSans", "NotoSerifExtended": "NotoSerif"}
_STYLE_SUFFIX = {"regular": "Regular", "bold": "Bold", "italic": "Italic", "bolditalic": "BoldItalic"}


def _noto_fallback(name: str, style: str, roots):
    """Noto's own file for an entry that names no single file: in the pinned
    checkouts, then the CI host's fonts-noto-core package."""
    base = _NOTO_FILES.get(name)
    if not base:
        return None
    wanted = f"{base}-{_STYLE_SUFFIX[style]}.ttf"
    for root in list(roots) + [pathlib.Path("/usr/share/fonts/truetype/noto")]:
        if (root / wanted).is_file():
            return root / wanted
        if root.is_dir() and root != pathlib.Path("/usr/share/fonts/truetype/noto"):
            for found in root.rglob(wanted):
                return found
    return None


def ship_reading_ttfs(catalog: dict, out: pathlib.Path, roots, cache: pathlib.Path) -> None:
    """One file per distinct source: a variable font's bold reuses its regular
    (the reader sets the weight axis), so it is not shipped twice."""
    out.mkdir(parents=True, exist_ok=True)
    manifest, total = [], 0
    for name, slug in READING_SLUGS.items():
        styles = catalog.get(name, {}).get("styles", {})
        shipped = {}
        for key, entry in styles.items():
            style = _style_key(key)
            source = _style_source(entry, roots, cache) or _noto_fallback(name, style, roots)
            if source is None:
                print(f"Smooth text: no TrueType source for {name} {key} ({entry!r}); it keeps 2-bit glyphs")
                continue
            if source.resolve() in shipped:
                print(f"Smooth text: {slug}-{style} uses {shipped[source.resolve()]} (variable font)")
                continue
            data = source.read_bytes()
            if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
                print(f"Smooth text: {source.name} is not TrueType/OpenType; skipped")
                continue
            dest = out / f"{slug}-{style}.ttf"
            dest.write_bytes(data)
            shipped[source.resolve()] = dest.name
            total += len(data)
            digest = hashlib.sha256(data).hexdigest()
            manifest.append(f"{digest}  {dest.name}  {name} {key} from {source.name}")
            print(f"Smooth text: {dest.name} ({len(data)} bytes) from {source.name}")
    if not any(line.split()[1].startswith(("sans-regular", "serif-regular")) for line in manifest):
        raise RuntimeError("No TrueType source for Noto Sans or Noto Serif regular")
    (out / "books-ttf.txt").write_text("\n".join(manifest) + "\n")
    print(f"Smooth text: {len(manifest)} TrueType files, {total} bytes")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_q2_small_font_assets.py OUTPUT_DIRECTORY", file=sys.stderr)
        return 2
    target = pathlib.Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="books-small-fonts-") as work:
        workspace = pathlib.Path(work)
        upstream = workspace / "crosspoint"
        run("git", "init", "-q", str(upstream))
        run("git", "-C", str(upstream), "remote", "add", "origin", CROSSPOINT_URL)
        run("git", "-C", str(upstream), "fetch", "--quiet", "--depth", "1",
            "origin", CROSSPOINT_REF)
        run("git", "-C", str(upstream), "checkout", "--quiet", "--detach", "FETCH_HEAD")

        scripts = upstream / "lib/EpdFont/scripts"
        config = yaml.safe_load((scripts / "sd-fonts.yaml").read_text())
        catalog = {item["name"]: item for item in config["families"]}
        crossink = workspace / "crossink"
        run("git", "init", "-q", str(crossink))
        run("git", "-C", str(crossink), "remote", "add", "origin", CROSSINK_URL)
        run("git", "-C", str(crossink), "fetch", "--quiet", "--depth", "1",
            "origin", CROSSINK_REF)
        run("git", "-C", str(crossink), "checkout", "--quiet", "--detach", "FETCH_HEAD")
        ink_catalog = yaml.safe_load((
            crossink/"lib/EpdFont/scripts/sd-fonts.yaml").read_text())
        ink_families = {item["name"]:item for item in ink_catalog["families"]}
        for name in CROSSINK_FAMILIES:
            if name not in ink_families:
                raise RuntimeError("CrossInk font missing from manifest: "+name)
            catalog[name] = ink_families[name]
        # Some script families appear in CrossPoint font *releases*, but are
        # absent from the particular pinned YAML snapshot. For those, use
        # Ubuntu 24.04's system Noto font sources on the CI host. The original
        # CrossPoint converter still produces all CPFONT v4 glyph/metrics and
        # joins the Latin fallback, exactly as it does for upstream families.
        # Never silently omit those 10/11pt fallbacks or use 12pt bitmaps.
        missing = sorted(set(FAMILIES) - set(catalog))
        for name in missing:
            if name == "NotoSansCJKJP":
                root = pathlib.Path("/usr/share/fonts/opentype/noto")
                regular_collection = root / "NotoSansCJK-Regular.ttc"
                # The pinned font converter expects TTF/OTF, not a TTC.
                # Extract the JP member (index 0) from Ubuntu's Noto
                # collection as a CI-host-only TTF, then rasterize it.
                from fontTools.ttLib import TTCollection
                extracted = workspace / "cjk-jp-regular.ttf"
                collection = TTCollection(str(regular_collection))
                try:
                    collection.fonts[0].save(str(extracted))
                finally:
                    collection.close()
                regular = extracted
                bold = pathlib.Path("/nonexistent")
                intervals = "cjk,latin-ext,punctuation,reading,symbols"
            else:
                root = pathlib.Path("/usr/share/fonts/truetype/noto")
                regular = root / f"{name}-Regular.ttf"
                bold = root / f"{name}-Bold.ttf"
                slug = FAMILIES[name]
                intervals = (INDIC_RANGES[slug] if slug in INDIC_RANGES
                             else slug)+",latin-ext,punctuation"
            if not regular.is_file():
                raise RuntimeError(f"Missing font source for {name}: {regular}")
            styles = {"regular": {"path": str(regular)}}
            if bold.is_file():
                styles["bold"] = {"path": str(bold)}
            catalog[name] = {
                "name": name,
                "description": f"Q2 CrossPoint source for {name}",
                "intervals": intervals,
                "styles": styles,
            }
        families = []
        for name in FAMILIES:
            source = dict(catalog[name])
            source["sizes"] = list(
                ALL_SIZES if name in CROSSINK_FAMILIES else SIZES)
            families.append(source)

        subset = workspace / "books-sizes-8-14.yaml"
        subset.write_text(yaml.safe_dump({"families": families}, sort_keys=False))
        built = workspace / "fonts"
        # CJK font rasterization is much heavier than Latin. Bound parallelism
        # and give each family enough time without raising peak Q2 RAM usage.
        run(sys.executable, str(scripts / "build-sd-fonts.py"),
            "--config", str(subset), "--output-dir", str(built),
            "--jobs", "2", "--timeout", "2400")

        checksums = []
        for name, slug in FAMILIES.items():
            for size in (ALL_SIZES if name in CROSSINK_FAMILIES else SIZES):
                source = built / name / f"{name}_{size}.cpfont"
                if not source.is_file():
                    raise RuntimeError(f"Missing freshly rasterized font: {source}")
                data = source.read_bytes()
                if len(data) < 10_000 or data[:8] != b"CPFONT\x00\x00":
                    raise RuntimeError(f"Invalid CPFONT v4 generated: {source}")
                dest = target / f"{slug}-{size}.cpfont"
                shutil.copyfile(source, dest)
                digest = hashlib.sha256(data).hexdigest()
                checksums.append(f"{digest}  {dest.name}")
                print(f"Generated CrossPoint {name} {size}pt: {len(data)} bytes")

        (target / "books-fonts-8-14.sha256").write_text(
            "\n".join(checksums) + "\n")
        write_license_bundle(target / "CrossPoint-font-licenses.txt",
                             upstream, crossink, catalog)
        ship_reading_ttfs(catalog, target / "ttf",
                          [upstream, scripts, crossink, crossink / "lib/EpdFont/scripts"],
                          workspace / "ttf-sources")
        # Validate these sizes exist for *all* 14 scripts and both primary
        # families, or fail the package rather than silently drop glyphs.
        assert len(checksums) == (len(FAMILIES) - len(CROSSINK_FAMILIES))*len(SIZES) + len(CROSSINK_FAMILIES)*len(ALL_SIZES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
