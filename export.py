import importlib.util
import subprocess
import sys
from pathlib import Path

# Paths
folder = Path(__file__).resolve().parent
inkscape = folder / "inkscape"
exports = folder / "exports"

# Configuration
sizes = (16, 32, 48, 64, 128, 256, 512, 1024, 2048)

# Dependencies
for module in ("scour", "cairosvg"):
    if importlib.util.find_spec(module) is None:
        sys.exit(f"Error: Missing dependency '{module}'. Install with: pip install {module}")

try:
    import cairosvg
except (ImportError, OSError) as error:
    sys.exit(f"Error: Failed to load CairoSVG: {error}")

# Validate input
if not inkscape.is_dir():
    sys.exit(f"Error: Directory not found: {inkscape}")

sources = sorted(inkscape.glob("*.svg"))

if not sources:
    sys.exit("Error: No SVG files found in the inkscape directory.")

try:
    exports.mkdir(parents=True, exist_ok=True)
except OSError as error:
    sys.exit(f"Error: Cannot create exports directory: {error}")

# Build
successful = 0
failed = 0

for source in sources:
    target = exports / source.name
    png_dir = exports / source.stem

    print(f"\nBuilding: {source.name}")

    try:
        # Optimize SVG
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scour.scour",
                "-i", str(source),
                "-o", str(target),
                "--set-precision=5",
                "--disable-group-collapsing",
                "--enable-comment-stripping",
                "--remove-metadata",
                "--strip-xml-space",
                "--indent=space",
                "--nindent=2",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        print(f"  SVG: {target.name}")

        # Export PNGs
        png_dir.mkdir(parents=True, exist_ok=True)

        for size in sizes:
            output = png_dir / f"{size}.png"

            cairosvg.svg2png(
                url=str(target),
                write_to=str(output),
                output_width=size,
                output_height=size,
            )

            print(f"  PNG: {size}x{size}")

        successful += 1

    except subprocess.CalledProcessError as error:
        failed += 1
        print(f"  Error: Scour failed: {error.stderr.strip() or error}")

    except (OSError, ValueError, cairosvg.SVGError) as error:
        failed += 1
        print(f"  Error: {error}")

# Summary
print(f"\nBuild complete: {successful} succeeded, {failed} failed.")

if failed:
    sys.exit(1)
