# Q2 Books Fonts

Optional reading and script font packs for [Q2 Books](https://github.com/lampsonlnguyen/q2-books). Font sources and licenses are pinned by the generator. Release assets will contain independently installable ZIPs, SHA-256 checksums and a versioned catalog. No firmware files are included.

The core app retains Noto Sans and its matching smooth-rendering assets. Optional packs preserve the existing 8–14 pt CPFONT layout and matching TrueType sources where available. Existing SD-card fonts remain usable offline. In-app installation is under development; no published packs are claimed yet.

## Development and provenance

The font-generation tools were imported from q2-books (GPL-3.0 source distribution); the generated font assets retain their own upstream font licenses, included in every pack. Upstream source revisions and pinned 12pt asset digests are retained unchanged. The source code license does not replace the separate font licenses.

Run the Build and publish font packs workflow to produce CI artifacts. A release tag named `fonts-v1.0.0` publishes those verified assets. The pack ZIP contents are relative to `.books/fonts/` and the manifest contains per-file sizes and SHA-256 digests. Existing font files can coexist with new ones. The CJK and Korean packs are separate. Thai is not an independently generated pack in the current upstream script list.
