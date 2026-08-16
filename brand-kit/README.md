# Joel brand kit

## Source logos

- `logo-red.svg` — primary Signal Red logo
- `logo-light.svg` — light-mode logo
- `logo-dark.svg` — dark-mode logo
- `animated/` — composable blink, 2D spin, and 3D spin web component

These SVG files are the editable source of truth. All variants use the same
shape, eye, shadow offset, and `-10°` tilt.

## Exported formats

- `png/{variant}/` — 16, 32, 48, 64, 128, 180, 192, 256, 512, and 1024 px
- `jpg/{variant}/` — 256, 512, and 1024 px
- `webp/{variant}/` — 256, 512, and 1024 px
- `favicons/` — SVG and multi-size ICO favicons, browser PNGs, Apple touch
  icon, Android icons, Windows tile icon, and web manifest

Use SVG for interfaces and print whenever possible. Use PNG for applications
that do not support SVG, JPG for flattened documents, and WebP for optimized
web delivery.

## Colors

- Signal Red: `#FF2D2D`
- Black: `#000000`
- Dark background: `#111111`
- Light background: `#F7F5F2`
- White: `#FFFFFF`

## Regenerating assets

After editing a source SVG, regenerate every raster export:

```sh
.brand-tools/bin/python brand-kit/generate_assets.py
```
