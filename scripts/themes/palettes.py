# The neo-brutalist palettes (Lagos Sunset, Owambe Gold) + WCAG contrast checks. Values are hex; the TS file gets "r g b".
P = {
 "sunset": {"name": "Lagos Sunset", "blurb": "Warm coral and amber",
   "dark":  dict(bg="140B08", surface="1A0F0B", card="21130E", elevated="2C1A13", overlay="38221A",
                 border="FFE4D6", subtle="3D2A20", text="FFF4EE", text2="E2C2B2", muted="A88676", disabled="54392D",
                 primary="FF7A45", hover="FF5F1F", plight="FFE1D2", pmuted="7A2E12", on="1A0B05", shadow="FFB38F"),
   "light": dict(bg="FFF7F2", surface="FFEFE6", card="FFFFFF", elevated="FDE3D6", overlay="F7D2C0",
                 border="2B1309", subtle="E9C3AF", text="2B1309", text2="5C3424", muted="8A5A47", disabled="C7A493",
                 primary="C2410C", hover="9A3412", plight="FFEDD5", pmuted="FED7AA", on="FFFFFF", shadow="2B1309")},
 "gold": {"name": "Owambe Gold", "blurb": "Black and gold, party-ready",
   "dark":  dict(bg="0B0905", surface="110E08", card="16120A", elevated="211B10", overlay="2D2516",
                 border="FDE68A", subtle="3A3020", text="FFFBEB", text2="E0CFA6", muted="A8946A", disabled="4E4330",
                 primary="FACC15", hover="EAB308", plight="FEF9C3", pmuted="713F12", on="1A1300", shadow="FACC15"),
   "light": dict(bg="FFFDF5", surface="FEF8E7", card="FFFFFF", elevated="FBF0CF", overlay="F4E3B0",
                 border="241A00", subtle="E8D9A8", text="241A00", text2="4D3D12", muted="76662F", disabled="C2B58A",
                 primary="A16207", hover="854D0E", plight="FEF3C7", pmuted="FDE68A", on="FFFFFF", shadow="241A00")},
}

def lum(h):
    c = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)

CHECKS = [  # (fg, bg, minimum, what)
    ("text", "bg", 12, "body text"), ("text", "card", 12, "text on cards"),
    ("text2", "bg", 7, "secondary text"), ("muted", "bg", 4.5, "muted text"), ("muted", "card", 4.5, "muted on card"),
    ("primary", "bg", 4.5, "accent text/links"), ("primary", "card", 4.5, "accent on card"),
    ("on", "primary", 4.5, "button label on accent"), ("border", "bg", 3, "borders (UI)"),
]
if __name__ == "__main__":
    bad = 0
    for pid, p in P.items():
        for mode in ("dark", "light"):
            v = p[mode]
            fails = [f"{what} {cr(v[f], v[b]):.2f}<{m}" for f, b, m, what in CHECKS if cr(v[f], v[b]) < m]
            bad += len(fails)
            print(f"{pid:7} {mode:5} {'OK' if not fails else 'FAIL: ' + '; '.join(fails)}")
    print("total failures:", bad)
