#!/usr/bin/env python3
"""Package existing CPFONT and TrueType assets without changing glyph data."""
import hashlib
import json
import pathlib
import sys
import zipfile

from crosspoint_script_fonts import SCRIPT_FONTS

NAMES = {"sans": "Noto Sans", "serif": "Noto Serif", "bitter": "Bitter",
         "lexenddeca": "Lexend Deca", "chareink": "ChareInk",
         "literata": "Literata", "merriweather": "Merriweather", "inter": "Inter",
         "atkinson": "Atkinson Hyperlegible", "cjk": "Chinese / Japanese",
         **{slug: description for slug, (_, description, _) in SCRIPT_FONTS.items()}}

def main():
    source, out = map(pathlib.Path, sys.argv[1:3])
    tag = sys.argv[3]
    if not tag.startswith("fonts-v") or not tag[7:].replace(".", "").isdigit():
        raise ValueError("Invalid font release tag")
    out.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/lampsonlnguyen/q2-books-fonts/releases/download/{tag}/"
    packs = []
    for slug, name in NAMES.items():
        fonts = [source / f"{slug}-{size}.cpfont" for size in range(8, 15)]
        for font in fonts:
            if not font.is_file() or font.stat().st_size > 16 * 1024 * 1024:
                raise ValueError(f"Missing or oversized font: {font}")
            with font.open("rb") as f:
                if f.read(8) != b"CPFONT\x00\x00":
                    raise ValueError(f"Invalid CPFONT: {font}")
        ttfs = sorted((source / "ttf").glob(f"{slug}-*.ttf"))
        licenses = source / "CrossPoint-font-licenses.txt"
        if not licenses.is_file():
            raise ValueError("Missing source licenses")
        files = [(f, f.name) for f in fonts]
        files += [(f, "ttf/" + f.name) for f in ttfs]
        files += [(licenses, "licenses/" + slug + ".txt")]
        archive = out / f"{slug}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for path, name_in_zip in files:
                z.write(path, name_in_zip)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError(f"Corrupt archive: {archive}")
        digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
        (out / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n")
        packs.append(dict(id=slug, name=name, sizes=list(range(8, 15)),
                          core=slug=="sans", smooth=bool(ttfs), bytes=archive.stat().st_size,
                          unpacked_bytes=sum(f.stat().st_size for f, _ in files),
                          sha256=digest, url=base+archive.name,
                          files=[{"path":n,"bytes":f.stat().st_size,
                                  "sha256":hashlib.file_digest(f.open("rb"),"sha256").hexdigest()}
                                 for f,n in files]))
    (out / "catalog.json").write_text(json.dumps(dict(schema=1, version=tag, packs=packs), indent=2)+"\n")
    print("Pack sizes:", [(p["id"], p["bytes"]) for p in packs])

if __name__ == "__main__":
    main()
