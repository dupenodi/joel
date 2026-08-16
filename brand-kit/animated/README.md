# Joel animated logo

A zero-dependency web component with three composable effects:

- `blink` — a single, simple blink
- `spin-2d` — continuous flat rotation of the star mark
- `spin-3d` — perspective rotation of the star mark

The rounded-square icon background always stays still.

## Use

Load the component once:

```html
<script type="module" src="/brand/joel-logo.js"></script>
```

Then choose one effect or combine several:

```html
<joel-logo variant="red" effects="blink"></joel-logo>
<joel-logo variant="light" effects="spin-2d"></joel-logo>
<joel-logo variant="dark" effects="spin-3d"></joel-logo>
<joel-logo variant="red" effects="blink spin-2d spin-3d"></joel-logo>
```

The `variant` values are `red`, `light`, and `dark`. Add `hover-pause` to pause
while the pointer is over the logo, or `paused` to pause it programmatically.

## Customize

Set size and timing with CSS custom properties:

```css
joel-logo {
  --joel-logo-size: 20rem;
  --joel-blink-duration: 4.8s;
  --joel-spin-2d-duration: 10s;
  --joel-spin-3d-duration: 7s;
  --joel-perspective: 1000px;
}
```

The component respects `prefers-reduced-motion`. Only add the `force-motion`
attribute when motion is essential and the user has explicitly opted in.

## Preview

Serve the repository root and open `brand-kit/animated/index.html`:

```sh
python3 -m http.server 8080
```
