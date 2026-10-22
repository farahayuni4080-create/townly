# Townly editorial theme

Townly uses a single palette source in `components.py`: `THEME_VARIABLES`. Light-theme accent, secondary, and progress/success UI colours use the requested butter yellow (`#FFEDAB`) instead of green. The two dictionaries are CSS-variable-compatible tokens, and `theme_variables("light")` / `theme_variables("dark")` returns the selected mapping. Flet views switch with `apply_theme(page, "light")` or `apply_theme(page, "dark")` (or `"system"`); this updates the page's Material theme, surfaces, inputs, buttons, and bottom navigation together.

## Light tokens

```css
:root, [data-theme="light"] {
  --bg: #FBF1E6;
  --card: #F5DABF;
  --text: #2B0C10;
  --muted: #7A4A4F;
  --primary: #6C151E;
  --on-primary: #F5DABF;
  --secondary: #FFEDAB;
  --on-secondary: #2B0C10;
  --border: #E3C3A3;
  --input: #FFF9F2;
  --input-border: #E3C3A3;
}
```

## Dark tokens

```css
[data-theme="dark"] {
  --bg: #082523;
  --card: #0F3D3A;
  --text: #F5DABF;
  --muted: #B9A58C;
  --primary: #F5DABF;
  --on-primary: #6C151E;
  --secondary: #6C151E;
  --on-secondary: #F5DABF;
  --border: #2A5F5A;
  --input: #0B312F;
  --input-border: #2A5F5A;
}
```

A web stylesheet using these tokens can switch themes by setting one root attribute, e.g. `<html data-theme="dark">`. The Flet app does not render its controls from CSS, so its equivalent one-step switch is its existing Light/Dark/System preference, routed through `apply_theme`.

## Component guidance

- Use one filled primary action per view; use `primary_button`, `secondary_button`, and `ghost_button` from `components.py` for consistent action hierarchy.
- Use `input_field` for form fields, `panel` / `metric` for bordered stat cards, and `status_chip` for compact badges.
- Headings use Roboto Condensed with a sans-serif fallback; body copy uses Roboto with a sans-serif fallback.
- Surfaces use flat fills, 10px corners, and thin palette borders. Avoid pure black/white, gradients, and heavy shadows.
