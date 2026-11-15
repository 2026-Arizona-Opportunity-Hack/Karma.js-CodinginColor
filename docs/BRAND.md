# Coding in Color brand rules for CIC Compass

Source: CIC brand guidelines PDF shared by CIC on Nov 15 (not stored in the repo). This file is the contract for the UI theme (NFR-10, D-141). When it conflicts with accessibility (NFR-4), accessibility wins and the conflict is noted here.

## Colors

| Token | Hex | Use in the app | Never |
|---|---|---|---|
| `--cic-dark-green` | `#007A3D` | Working color: headings, nav bar, table headers, borders, focus rings, links | |
| `--cic-green` | `#00A850` | Primary buttons (bold 19 px+ text), key accents, small status marks | Large background fills; any text color on white (3.13:1) |
| `--cic-white` | `#FFFFFF` | Page and card backgrounds, text on dark green | |
| `--cic-tint` | `#E6F4ED` | Alternating table rows, callouts, selected rows | Primary or dominant color |
| `--cic-gray-light` | `#C8C8C8` | Dividers, disabled borders, logo accent | Body text on white (fails contrast) |
| `--cic-gray-mid` | `#595959` | Secondary body text, captions | |
| `--cic-black` | `#000000` | Body text | |

Rules: dark green is the main color; green is used sparingly; no neon greens for text; leave white space, do not flood screens with green. Error and warning colors are not in the brand palette: keep the existing accessible red and amber.

Contrast notes (computed): white on `#007A3D` is 5.45:1 and dark green on `#E6F4ED` is 4.81:1, both AA for normal text. White on `#00A850` is only 3.13:1, which passes AA for large text only, so `#00A850` buttons use **bold text of at least 19 px** (14 pt bold), or use `#007A3D` as the button fill. Green text on white is also 3.13:1, so never use `#00A850` for body text or small labels. Lighthouse must stay at 95+.

```css
:root {
  --cic-dark-green: #007A3D;
  --cic-green: #00A850;
  --cic-tint: #E6F4ED;
  --cic-gray-light: #C8C8C8;
  --cic-gray-mid: #595959;
  --cic-black: #000000;
  --cic-white: #FFFFFF;
}
```

## Type

- One sans family: `Arial, "Helvetica Neue", system-ui, sans-serif`. At most two families; no decorative or script fonts.
- Headings bold, dark green; subheadings semibold, dark green or black; clear H1 > H2 > H3.
- Body 16 px (14 px minimum in dense tables), black or `#595959`, line height at least 1.15 (use 1.5 for body).
- Captions 12 to 13 px, black or `#595959`.

## Logo

- Files come from CIC's logo album (link in the brand PDF); add the chosen SVG/PNG to `frontend/public/brand/` only after CIC confirms we may use it in the repo.
- Never smaller than 24 px high; clear space on all sides equal to the height of the "C" in "Coding".
- Do not stretch, recolor outside the palette, add shadows or effects, or place on a busy background (use white or dark green behind it).

## Voice (UI copy, emails, README, demo)

Professional, empowering, tech-forward, community-rooted. Credible and modern, warm but not casual, never corporate-stiff. Avoid jargon and exclusionary framing. Say "board member", "donor", "gift", "thank-you"; avoid internal terms like "row_key" or "attribution" in the UI.

Document naming for exported files: `CIC_<DocumentType>_<Topic>_<Date>` (for example `CIC_FunderReport_AIAcademy_2026-11-15.csv`).
