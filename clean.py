#!/usr/bin/env python3
"""Strip Inkscape workspace metadata from the source SVGs.

Removes only editor state (version stamps, window geometry, zoom and
pan position). Guides, layer labels, ids and geometry stay untouched,
so editing in Inkscape and the build scripts are unaffected. Run it
any time after saving from Inkscape, before committing.
"""

import sys
from pathlib import Path

try:
    from lxml import etree  # ships with cairosvg
except ImportError:
    sys.exit("Error: lxml is required. Install with: pip install cairosvg")

FOLDER = Path(__file__).resolve().parent / "inkscape"

NS = {
    "inkscape": "http://www.inkscape.org/namespaces/inkscape",
    "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
}

DROP_ON_SVG = ("inkscape:version", "sodipodi:docname")
DROP_ON_NAMEDVIEW = (
    "inkscape:zoom",
    "inkscape:cx",
    "inkscape:cy",
    "inkscape:window-width",
    "inkscape:window-height",
    "inkscape:window-x",
    "inkscape:window-y",
    "inkscape:window-maximized",
    "inkscape:current-layer",
)


def qname(dotted):
    prefix, local = dotted.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def clean(path):
    tree = etree.parse(str(path))
    root = tree.getroot()
    dropped = []

    for name in DROP_ON_SVG:
        if root.attrib.pop(qname(name), None) is not None:
            dropped.append(name)

    namedview = root.find("sodipodi:namedview", NS)
    if namedview is not None:
        for name in DROP_ON_NAMEDVIEW:
            if namedview.attrib.pop(qname(name), None) is not None:
                dropped.append(name)

    if not dropped:
        print(f"Already clean: {path.name}")
        return

    tree.write(str(path), xml_declaration=True, encoding="UTF-8", standalone=False)
    print(f"Cleaned: {path.name} ({', '.join(dropped)})")


def main():
    if not FOLDER.is_dir():
        sys.exit(f"Error: Directory not found: {FOLDER}")
    sources = sorted(FOLDER.glob("*.svg"))
    if not sources:
        sys.exit(f"Error: No SVG files found in {FOLDER}")
    for source in sources:
        clean(source)


if __name__ == "__main__":
    main()
