from palettes import cr
def blend(fg, bg, a):  # fg over bg at alpha a -> hex
    f = [int(fg[i:i+2],16) for i in (0,2,4)]; b = [int(bg[i:i+2],16) for i in (0,2,4)]
    return "".join(f"{round(fv*a + bv*(1-a)):02X}" for fv, bv in zip(f, b))

# Style themes. "card" is the panel tint drawn at card_alpha over the page; worst-case page
# colours (base and the strongest blob) are checked, so text stays readable on any part.
S = {
 "glass": {"name": "Glass", "blurb": "Frosted panels over a glowing gradient", "style": "glass",
   "dark": dict(bg="0B1020", page=["0B1020", "2E1D5C", "0D2C45"], card="FFFFFF", card_alpha=0.10,
                elevated_alpha=0.16, border="FFFFFF", border_alpha=0.30,
                text="FFFFFF", text2="D3D9EA", muted="B8C1D9", disabled="5B6480",
                primary="A5B4FC", hover="818CF8", plight="E0E7FF", pmuted="312E81", on="0B1020", subtle="FFFFFF"),
   "light": dict(bg="EEF2FF", page=["EEF2FF", "D9CCFB", "C4E7FA"], card="FFFFFF", card_alpha=0.55,
                elevated_alpha=0.70, border="8B93D9", border_alpha=0.55,
                text="0F172A", text2="334155", muted="475569", disabled="94A3B8",
                primary="4338CA", hover="3730A3", plight="E0E7FF", pmuted="C7D2FE", on="FFFFFF", subtle="FFFFFF")},
 "fluffy": {"name": "Fluffy", "blurb": "Soft pastels, round and pillowy", "style": "fluffy",
   "dark": dict(bg="1C1530", page=["1C1530", "2A1E45", "1E2340"], card="2A2142", card_alpha=1.0,
                elevated_alpha=1.0, border="4A3D6E", border_alpha=1.0,
                text="FFF7FB", text2="E3D6EE", muted="B3A6C9", disabled="5D5179",
                primary="F9A8D4", hover="F472B6", plight="FCE7F3", pmuted="6B2150", on="2A0A1C", subtle="3A2F57"),
   "light": dict(bg="FFF5FA", page=["FFF5FA", "F3EEFF", "EAF6FF"], card="FFFFFF", card_alpha=0.92,
                elevated_alpha=1.0, border="E3B9CF", border_alpha=1.0,
                text="3B2A4A", text2="5B476A", muted="76628A", disabled="C9B8D6",
                primary="BE3A79", hover="9D2B62", plight="FCE7F3", pmuted="FBCFE8", on="FFFFFF", subtle="F6E3EE")},
}
if __name__ == "__main__":
    bad = 0
    for sid, s in S.items():
        for mode in ("dark", "light"):
            v = s[mode]; fails = []
            for page in v["page"]:
                panel = blend(v["card"], page, v["card_alpha"])
                border = blend(v["border"], panel, v["border_alpha"])
                checks = [("text", v["text"], panel, 7), ("text2", v["text2"], panel, 4.5),
                          ("muted", v["muted"], panel, 4.5), ("accent", v["primary"], panel, 4.5),
                          ("text on page", v["text"], page, 7), ("accent on page", v["primary"], page, 4.5),
                          ("button label", v["on"], v["primary"], 4.5), ("border vs panel", border, page, 1.25)]
                fails += [f"{n}@{page} {cr(a,b):.2f}<{m}" for n, a, b, m in checks if cr(a, b) < m]
            bad += len(fails)
            print(f"{sid:6} {mode:5} {'OK' if not fails else 'FAIL: ' + '; '.join(fails)}")
    print("total failures:", bad)
