from palettes import cr
def blend(fg, bg, a):  # fg over bg at alpha a -> hex
    f = [int(fg[i:i+2],16) for i in (0,2,4)]; b = [int(bg[i:i+2],16) for i in (0,2,4)]
    return "".join(f"{round(fv*a + bv*(1-a)):02X}" for fv, bv in zip(f, b))

# Style themes. "card" is the panel tint drawn at card_alpha over the page; worst-case page
# colours (base and the strongest blob) are checked, so text stays readable on any part.
#
# Optional surface/elevated/overlay give the solid styles (fluid, pop) their layer colours.
S = {
 # The default. Fluid: rounded corners, thin soft borders, diffuse shadows, a faint purple glow.
 "turnup": {"name": "Turnup", "blurb": "Electric purple, smooth and rounded; AMOLED black at night", "style": "fluid",
   # Dark is AMOLED black: a true-black page with no glow (black pixels switch off on AMOLED
   # screens), near-black cards so they still stand out.
   "dark": dict(bg="000000", page=["000000", "000000", "000000"], glow=False, card="0E0C12", card_alpha=1.0,
                surface="07060A", elevated="17141D", overlay="211D29", elevated_alpha=1.0,
                border="2E2938", border_alpha=1.0, subtle="1A1720",
                text="FFFFFF", text2="C9C3D6", muted="9A93AB", disabled="4A4458",
                primary="A855F7", hover="9333EA", plight="EDE9FE", pmuted="3B1764", on="FFFFFF", shadow="000000"),
   "light": dict(bg="F7F5FB", page=["F7F5FB", "EFE6FD", "EAEEFF"], card="FFFFFF", card_alpha=1.0,
                surface="F1EEF7", elevated="EFEBF6", overlay="E4DFEE", elevated_alpha=1.0,
                border="CFC6E0", border_alpha=1.0, subtle="EAE6F1",
                text="14111C", text2="3D3750", muted="5F5873", disabled="B3ACC2",
                primary="7E22CE", hover="6B21A8", plight="F3E8FF", pmuted="E9D5FF", on="FFFFFF", shadow="2E1065")},
 # Quiz-show: playful and chunky. Cream page with confetti glows (mint, butter, bubblegum), inky
 # outlines, pill buttons on a solid 3D edge, rounded bold type. Dark: midnight navy + electric lime.
 "pop": {"name": "Game Night", "blurb": "Confetti colours, chunky pill buttons, like a quiz show", "style": "pop",
   "dark": dict(bg="14163A", page=["14163A", "2A1F5E", "123E4A", "3A1A4E"], card="1E2152", card_alpha=1.0,
                surface="191C47", elevated="282C66", overlay="313676", elevated_alpha=1.0,
                border="555BC0", border_alpha=1.0, subtle="2C3070",
                text="FFFFFF", text2="DCDDF5", muted="AEB1DE", disabled="555A9A",
                primary="D4F25C", hover="C2E83A", plight="F3FCD2", pmuted="4A5A12", on="17190A", shadow="05061A"),
   "light": dict(bg="FFF7EA", page=["FFF7EA", "D8F6E8", "FFEDB8", "FFDDE8"], card="FFFFFF", card_alpha=1.0,
                surface="FFFCF5", elevated="FFF1D9", overlay="FBE6C4", elevated_alpha=1.0,
                border="1B1A3A", border_alpha=1.0, subtle="F0E2CB",
                text="1B1A3A", text2="3A3960", muted="58577D", disabled="B9B8CF",
                primary="2747D6", hover="1E37AD", plight="DCE4FF", pmuted="B9C8FF", on="FFFFFF", shadow="1B1A3A")},
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
