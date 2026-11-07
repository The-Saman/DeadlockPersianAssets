#!/usr/bin/env python3
"""Build interactive logo SVGs from exports, without reading Inkscape sources."""

import argparse
import html
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
# After moving this file to the project root, use its exports directory.
# Also allow running it from exports before the move.
EXPORTS = HERE if HERE.name == "exports" else HERE / "exports"

MOTION_CSS = r"""    #g6 { transform-box: view-box; transform-origin: 125px 125px;
      transform: scale(1); transition: transform 180ms cubic-bezier(.16,1,.3,1); }
    svg.is-active #g6 { transform: scale(var(--eye-scale, 1.12)); }
    @media (prefers-reduced-motion: reduce) { #g6 { transition-duration: 0.01ms; } }
"""

MOTION_JS = r"""(() => {
  const logo = document.currentScript.closest('svg');
  const rotor = logo.querySelector('#g20');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const speed = 220; // Immediate clockwise rotation: about 1.64 seconds per revolution
  let active = false, angle = 0, velocity = 0, frame = 0, last = null, settling = null;
  const paint = () => rotor.setAttribute('transform', `rotate(${angle} 125 125)`);
  function tick(now) {
    const dt = last === null ? 0 : Math.min((now - last) / 1000, .05);
    last = now;
    if (active) {
      angle = (angle + speed * dt) % 360;
      velocity = speed;
    } else if (settling) {
      settling.elapsed += dt;
      const { start, target, duration, elapsed } = settling;
      const t = Math.min(elapsed / duration, 1);
      // Decelerate over the remaining quarter-turn, never faster than hover.
      angle = start + (target - start) * (1 - Math.pow(1 - t, 2));
      velocity = 0;
      if (t === 1) { angle = target % 360; velocity = 0; settling = null; }
    }
    paint();
    if (active || settling) frame = requestAnimationFrame(tick);
    else { frame = 0; last = null; }
  }
  function setActive(value) {
    value = Boolean(value);
    if (value === active) return;
    active = value;
    logo.classList.toggle('is-active', active);
    if (reduced.matches) {
      cancelAnimationFrame(frame); frame = 0; last = null;
      angle = velocity = 0; settling = null; paint(); return;
    }
    if (active) settling = null;
    else if (angle !== 0 || velocity !== 0) {
      // The design repeats every 90 degrees: stop at the next clockwise quadrant.
      const target = Math.ceil(angle / 90) * 90;
      const distance = target - angle;
      settling = { start: angle, target, duration: Math.max(.1, 2 * distance / speed), elapsed: 0 };
    }
    if (!frame && (active || settling)) frame = requestAnimationFrame(tick);
  }
  logo.setDeadlockActive = setActive;
  logo.addEventListener('pointerenter', () => { if (!logo.hasAttribute('data-manual')) setActive(true); });
  logo.addEventListener('pointerleave', () => { if (!logo.hasAttribute('data-manual')) setActive(false); });
  reduced.addEventListener('change', () => {
    cancelAnimationFrame(frame); frame = 0; last = null;
    angle = velocity = 0; settling = null; paint();
    if (active && !reduced.matches) frame = requestAnimationFrame(tick);
  });
})();
"""

PREVIEW_HTML = r"""<!doctype html>
<html lang="fa" dir="rtl">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100svh; display: grid; place-items: center; background: #181617; color: #efdebf; font-family: Tahoma, sans-serif; }
  main { text-align: center; padding: 32px; }
  button { display: block; margin: 0 auto; width: min(70vw, 360px); background: transparent; border: 0; padding: 0; border-radius: 50%; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  button:focus-visible { outline: 2px solid #efdebf; outline-offset: 12px; }
  svg { display: block; width: 100%; height: auto; }
</style>
<main>
  <button id="trigger" aria-label="اجرای حرکت نشان ددلاک">
{{SVG}}


  </button>
</main>
<script>
  const logo = document.querySelector('#svg1');
  const trigger = document.querySelector('#trigger');
  // Your app can call setDeadlockActive(true / false) for any event.
  window.setDeadlockActive = (active) => logo.setDeadlockActive(active);
  let hovered = false, focused = false, pressed = false;
  const update = () => setDeadlockActive(hovered || focused || pressed);
  trigger.addEventListener('pointerenter', e => { if (e.pointerType !== 'touch') { hovered = true; update(); } });
  trigger.addEventListener('pointerleave', () => { hovered = false; update(); });
  trigger.addEventListener('focus', () => { focused = trigger.matches(':focus-visible'); update(); });
  trigger.addEventListener('blur', () => { focused = false; update(); });
  trigger.addEventListener('pointerdown', e => { if (e.pointerType === 'touch') { pressed = true; trigger.setPointerCapture(e.pointerId); update(); } });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    trigger.addEventListener(event, () => { pressed = false; update(); });
  }
</script>
</html>
"""
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def tag(name):
    return f"{{{NS}}}{name}"


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def curved_perimeter(data):
    """Read one exported half-eye, removing only its straight closing seam.

    Supports the M/C/S/H/L/Z commands emitted for these designs, in either
    relative or absolute form. Unknown geometry fails instead of changing art.
    Each returned segment is a cubic (start, control1, control2, end).
    """
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?", data)
    segments = []
    i, current, origin, previous_control = 0, (0., 0.), None, None
    command = None
    counts = {"M": 2, "L": 2, "H": 1, "C": 6, "S": 4}
    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        if command is None:
            raise ValueError("Invalid eye path")
        kind, relative = command.upper(), command.islower()
        if kind == "Z":
            if distance(current, origin) > .02:
                segments.append((current, None, None, origin))
            current, previous_control, command = origin, None, None
            continue
        if kind not in counts:
            raise ValueError(f"Unsupported eye path command: {command}")
        n = counts[kind]
        values = list(map(float, tokens[i:i+n]))
        if len(values) != n:
            raise ValueError("Incomplete eye path")
        i += n
        def point(x, y):
            return (x + current[0], y + current[1]) if relative else (x, y)
        if kind == "M":
            current = point(*values)
            if origin is not None:
                raise ValueError("Expected a single contour per half-eye")
            origin = current
            command = "l" if relative else "L"
            previous_control = None
            continue
        if kind == "C":
            a, b, end = (point(*values[j:j+2]) for j in (0, 2, 4))
        elif kind == "S":
            a = (2*current[0]-previous_control[0], 2*current[1]-previous_control[1]) if previous_control else current
            b, end = point(*values[:2]), point(*values[2:])
        else:
            a = b = None
            end = point(*values) if kind == "L" else (values[0] + (current[0] if relative else 0), current[1])
        segments.append((current, a, b, end))
        current, previous_control = end, b
    seams = [i for i, (p, a, b, q) in enumerate(segments)
             if a is None and abs(p[1]-125) < .02 and abs(q[1]-125) < .02 and abs(p[0]-q[0]) > 100]
    if len(seams) != 1:
        raise ValueError("Expected one horizontal seam in each half-eye")
    seam = seams[0]
    perimeter = segments[seam+1:] + segments[:seam]
    if not perimeter or any(a is None for _, a, _, _ in perimeter):
        raise ValueError("Expected a curved eye outline")
    return perimeter


def join_eye(lower, upper):
    """Join actual exported curves, retaining both halves' original outlines."""
    first = curved_perimeter(lower)
    second = curved_perimeter(upper)
    if distance(first[-1][3], second[0][0]) > .02:
        second = [(q, b, a, p) for p, a, b, q in reversed(second)]
    if distance(first[-1][3], second[0][0]) > .02 or distance(second[-1][3], first[0][0]) > .02:
        raise ValueError("Eye halves do not meet at their corners")
    fmt = lambda p: f"{p[0]:.6f},{p[1]:.6f}"
    return "M" + fmt(first[0][0]) + "".join(
        " C" + " ".join(map(fmt, (a, b, q))) for _, a, b, q in first + second
    ) + " Z"


def build(source, output):
    root = ET.fromstring(source.read_text(encoding="utf-8"))
    if root.tag != tag("svg") or list(map(float, root.get("viewBox", "").split())) != [0, 0, 250, 250]:
        raise ValueError("Expected a logo SVG with viewBox='0 0 250 250'")
    if root.find(f".//{tag('script')}") is not None:
        raise ValueError("Input already contains a script; use the static export")
    by_id = {node.get("id"): node for node in root.iter() if node.get("id")}
    required = {"layer1", "g20", "g6", "g2", "g1", "path1", "path28", "path29"}
    if missing := required - by_id.keys():
        raise ValueError(f"Missing logo layers: {', '.join(sorted(missing))}")
    eye = by_id["g2"]
    lower, upper = by_id["path29"], by_id["path28"]
    if lower not in eye or upper not in eye:
        raise ValueError("Eye halves must be direct children of g2")
    if any(k in node.attrib for node in (lower, upper) for k in ("transform", "fill", "stroke")):
        raise ValueError("Eye halves have individual styling/transforms; cannot safely merge")
    unified = ET.Element(tag("path"), {"id": "eye-body", "d": join_eye(lower.get("d", ""), upper.get("d", ""))})
    eye.insert(list(eye).index(lower), unified)
    eye.remove(lower)
    eye.remove(upper)
    # The backing circle and optional three-color flag stay outside the rotor.
    layer = by_id["layer1"]
    background = ET.Element(tag("g"), {"id": "flag-background" if "g7" in by_id else "logo-background"})
    layer.insert(list(layer).index(by_id["path1"]), background)
    for name in ("path1", "g7"):
        if name in by_id:
            node = by_id[name]
            if node not in layer:
                raise ValueError(f"Expected {name} directly inside layer1")
            layer.remove(node)
            background.append(node)
    style = ET.Element(tag("style"))
    style.text = "\n" + MOTION_CSS
    root.insert(0, style)
    # CDATA works in standalone XML SVG and the HTML inline preview alike.
    script = MOTION_JS
    script_markup = "<script>//<![CDATA[\n" + script + "//]]></script>\n"
    def serialize():
        return ET.tostring(root, encoding="unicode").replace("</svg>", script_markup + "</svg>")
    svg = serialize()
    title = f"{source.stem} preview"
    root.set("data-manual", "")
    root.set("role", "img")
    root.set("aria-label", title)
    preview = PREVIEW_HTML
    preview = preview.replace("{{TITLE}}", html.escape(title)).replace("{{SVG}}", serialize())
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{source.stem}-animated.svg"
    target.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n", encoding="utf-8")
    (output / f"{source.stem}-preview.html").write_text(preview, encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", type=Path, help="Static exported SVGs (default: exports/*.svg relative to the script, excluding *-animated.svg)")
    parser.add_argument("--output-dir", type=Path, help="Output folder (default: beside each input)")
    args = parser.parse_args()
    sources = args.sources or sorted(p for p in EXPORTS.glob("*.svg") if not p.stem.endswith("-animated"))
    if not sources:
        parser.error("No exported SVGs found")
    failures = 0
    for source in sources:
        try:
            target = build(source, args.output_dir or source.parent)
            print(f"Built: {target} + {source.stem}-preview.html")
        except (OSError, ValueError, ET.ParseError) as error:
            failures += 1
            print(f"Error: {source}: {error}", file=sys.stderr)
    return int(failures > 0)


if __name__ == "__main__":
    sys.exit(main())
