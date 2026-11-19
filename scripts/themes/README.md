# Theme generator

`frontend/src/lib/themes.ts` is generated from these files. Every theme is checked for WCAG
contrast before it's written (body text ≥ 7:1; secondary, muted and accent text ≥ 4.5:1;
button labels ≥ 4.5:1; for Glass, against the translucent panel over every part of the
page gradient).

- `palettes.py`: the six neo-brutalist colour themes, plus the contrast checker
- `styles.py`: Glass and Fluffy, which also change shape, shadows, blur and the page background

To change or add a theme, edit those files, then:

```bash
cd scripts/themes
python palettes.py && python styles.py    # contrast report (see the note below)
python gen_palettes_json.py . > palettes.json
python gen_themes_ts.py > ../../frontend/src/lib/themes.ts
rm palettes.json
```

`palettes.py` reports one known failure: the original Turnup dark theme's white button text
on purple (3.96:1). It's kept on purpose as the existing brand look; every other theme passes.

A new theme id must also be added to `THEME_IDS` in `backend/app/schemas/user.py`
(`backend/tests/test_themes.py` fails until it is).
