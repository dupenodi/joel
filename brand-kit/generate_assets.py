"""Generate raster logo exports and favicon assets from the source SVGs."""

from io import BytesIO
from pathlib import Path
import json
import shutil

import cairosvg
from PIL import Image


ROOT = Path(__file__).resolve().parent
VARIANTS = ("red", "light", "dark")
PNG_SIZES = (16, 32, 48, 64, 128, 180, 192, 256, 512, 1024)
RASTER_SIZES = (256, 512, 1024)


def render_svg(source: Path, size: int) -> Image.Image:
    data = cairosvg.svg2png(
        url=str(source),
        output_width=size,
        output_height=size,
    )
    return Image.open(BytesIO(data)).convert("RGBA")


def save_png_exports() -> None:
    for variant in VARIANTS:
        source = ROOT / f"logo-{variant}.svg"
        output = ROOT / "png" / variant
        output.mkdir(parents=True, exist_ok=True)

        for size in PNG_SIZES:
            image = render_svg(source, size)
            image.save(output / f"logo-{variant}-{size}x{size}.png", optimize=True)


def save_presentation_exports() -> None:
    for variant in VARIANTS:
        source = ROOT / f"logo-{variant}.svg"
        jpg_output = ROOT / "jpg" / variant
        webp_output = ROOT / "webp" / variant
        jpg_output.mkdir(parents=True, exist_ok=True)
        webp_output.mkdir(parents=True, exist_ok=True)

        for size in RASTER_SIZES:
            image = render_svg(source, size)
            image.convert("RGB").save(
                jpg_output / f"logo-{variant}-{size}x{size}.jpg",
                quality=95,
                optimize=True,
            )
            image.save(
                webp_output / f"logo-{variant}-{size}x{size}.webp",
                quality=95,
                method=6,
            )


def save_favicons() -> None:
    output = ROOT / "favicons"
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "logo-red.svg"

    favicon_sizes = {
        "favicon-16x16.png": 16,
        "favicon-32x32.png": 32,
        "favicon-48x48.png": 48,
        "apple-touch-icon.png": 180,
        "android-chrome-192x192.png": 192,
        "android-chrome-512x512.png": 512,
        "mstile-150x150.png": 150,
    }
    for filename, size in favicon_sizes.items():
        render_svg(source, size).save(output / filename, optimize=True)

    icon_source = render_svg(source, 256)
    icon_source.save(
        output / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    shutil.copyfile(source, output / "favicon.svg")

    manifest = {
        "name": "Joel",
        "short_name": "Joel",
        "icons": [
            {
                "src": "android-chrome-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "android-chrome-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
        "theme_color": "#FF2D2D",
        "background_color": "#FF2D2D",
        "display": "standalone",
    }
    (output / "site.webmanifest").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    save_png_exports()
    save_presentation_exports()
    save_favicons()
    print("Brand assets generated successfully.")


if __name__ == "__main__":
    main()
