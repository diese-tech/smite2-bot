# GodForge Asset Manifest

Production assets are intentionally deferred, but the dashboard layout now has stable slots so real graphics can drop in without reshaping the UI.

## Current Slots

| Slot | CSS Class | Intended Use | Target Spec | Status |
|---|---|---|---|---|
| `god-card` | `asset-slot--god-card` | Roll Team and random god portraits | `160x240` portrait or same `2:3` ratio | Placeholder / SmiteFire temporary portraits |
| `role-icon` | `asset-slot--role-icon` | Role markers for god cards | `32x32` SVG or transparent PNG | Placeholder initials |
| `item-card` | `asset-slot` on build slots | Build item cards | Square or compact item tile | Text placeholder |
| `dashboard-hero` | `asset-slot` | Landing/dashboard hero art | Wide dashboard crop | Placeholder |
| `background-texture` | CSS background hook | Smite 2 themed texture layer | Seamless wide texture | CSS-only placeholder |
| `conquest-map` | Future slot | Match/draft map context | Responsive map image | Deferred |
| `draft-map` | Future slot | Draft phase surface | Responsive tactical map | Deferred |
| `roll-map` | Future slot | Randomizer tactical surface | Responsive tactical map | Deferred |

## Naming Recommendation

Use lowercase kebab-case filenames:

```text
god-card-thor.png
role-icon-jungle.svg
item-card-deathbringer.png
dashboard-hero-smite-night.webp
background-texture-forge.webp
conquest-map-main.webp
draft-map-picks.webp
roll-map-randomizer.webp
```

## Integration Notes

- Keep the DOM classes stable and swap only `background-image` or `img src`.
- Prefer owned or licensed Smite 2-compatible graphics before production use.
- Missing assets should fall back to the current placeholder surfaces.
- Do not commit large production art until the asset source and licensing are confirmed.
