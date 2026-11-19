# Theme generator

`frontend/src/lib/themes.ts` is generated from these files. Every theme is checked for WCAG
contrast before it's written (body text ≥ 7:1; secondary, muted and accent text ≥ 4.5:1;
button labels ≥ 4.5:1; for Glass, against the translucent panel over every part of the
page gradient).

- `palettes.py`: the neo-brutalist colour themes (Lagos Sunset, Owambe Gold), plus the contrast checker
- `styles.py`: the themes that also change shape, shadows, blur and the page background:
  Turnup (the default, "fluid": rounded, hairline borders, soft shadows), Game Night ("pop":
  quiz-show chunky with 3D button edges and rounded bold type), Glass and Fluffy

Style-specific CSS (border widths, fonts, button pressing) lives in
`frontend/src/app/globals.css` under "Theme styles". If you change Turnup's colours, also copy
its tokens into the defaults at the top of that file (they're used before JavaScript runs).

To change or add a theme, edit those files, then:

```bash
cd scripts/themes
python palettes.py && python styles.py    # contrast report (see the note below)
python gen_palettes_json.py . > palettes.json
python gen_themes_ts.py > ../../frontend/src/lib/themes.ts
rm palettes.json
```

`styles.py` reports one known failure: Turnup dark's white button labels on the brand's
electric purple (3.96:1). It's kept on purpose as the brand look; every other theme passes.

A new theme id must also be added to `THEME_IDS` in `backend/app/schemas/user.py`
(`backend/tests/test_themes.py` fails until it is).
