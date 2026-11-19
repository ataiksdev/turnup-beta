# Candidate palettes + WCAG contrast checks. Values are hex; the TS file gets "r g b".
P = {
 "turnup": {"name": "Turnup", "blurb": "The original: electric purple",
   "dark":  dict(bg="0A0A0A", surface="101010", card="141414", elevated="1C1C1C", overlay="262626",
                 border="FFFFFF", subtle="2D2D2D", text="FFFFFF", text2="B9B9B9", muted="8A8A8A", disabled="414141",
                 primary="A855F7", hover="9333EA", plight="EDE9FE", pmuted="581C87", on="FFFFFF", shadow="FFFFFF"),
   "light": dict(bg="FFFFFF", surface="F8F8F8", card="FFFFFF", elevated="EEEEEE", overlay="DEDEDE",
                 border="000000", subtle="C8C8C8", text="000000", text2="3C3C3C", muted="6B6B6B", disabled="AAAAAA",
                 primary="7E22CE", hover="6B21A8", plight="F3E8FF", pmuted="E9D5FF", on="FFFFFF", shadow="000000")},
 "sunset": {"name": "Lagos Sunset", "blurb": "Warm coral and amber",
   "dark":  dict(bg="140B08", surface="1A0F0B", card="21130E", elevated="2C1A13", overlay="38221A",
                 border="FFE4D6", subtle="3D2A20", text="FFF4EE", text2="E2C2B2", muted="A88676", disabled="54392D",
                 primary="FF7A45", hover="FF5F1F", plight="FFE1D2", pmuted="7A2E12", on="1A0B05", shadow="FFB38F"),
   "light": dict(bg="FFF7F2", surface="FFEFE6", card="FFFFFF", elevated="FDE3D6", overlay="F7D2C0",
                 border="2B1309", subtle="E9C3AF", text="2B1309", text2="5C3424", muted="8A5A47", disabled="C7A493",
                 primary="C2410C", hover="9A3412", plight="FFEDD5", pmuted="FED7AA", on="FFFFFF", shadow="2B1309")},
 "lagoon": {"name": "Lagoon", "blurb": "Deep ocean blues and teal",
   "dark":  dict(bg="06101A", surface="0A1622", card="0E1C2B", elevated="152637", overlay="1D3246",
                 border="D6F1FF", subtle="1F3448", text="EEF8FF", text2="B4CEDF", muted="7C97AA", disabled="34495B",
                 primary="22D3EE", hover="06B6D4", plight="CFFAFE", pmuted="155E75", on="04141A", shadow="67E8F9"),
   "light": dict(bg="F3FAFF", surface="E8F4FC", card="FFFFFF", elevated="D9ECF8", overlay="C6E0F2",
                 border="06243A", subtle="B8D4E8", text="06243A", text2="25475F", muted="4E6E86", disabled="9FB9CC",
                 primary="0E7490", hover="155E75", plight="CFFAFE", pmuted="A5F3FC", on="FFFFFF", shadow="06243A")},
 "palm": {"name": "Palm", "blurb": "Lush greens, easy on the eyes",
   "dark":  dict(bg="07110B", surface="0B1710", card="0F1E15", elevated="16291D", overlay="1E3527",
                 border="DCFCE7", subtle="1F3527", text="F0FDF4", text2="B8D8C3", muted="7FA08A", disabled="35503F",
                 primary="4ADE80", hover="22C55E", plight="DCFCE7", pmuted="14532D", on="052E16", shadow="86EFAC"),
   "light": dict(bg="F5FBF6", surface="EAF6EE", card="FFFFFF", elevated="DCEFE2", overlay="C9E5D2",
                 border="0A2A17", subtle="BEDCC7", text="0A2A17", text2="2B4A37", muted="4F6E5A", disabled="A3C0AD",
                 primary="15803D", hover="166534", plight="DCFCE7", pmuted="BBF7D0", on="FFFFFF", shadow="0A2A17")},
 "gold": {"name": "Owambe Gold", "blurb": "Black and gold, party-ready",
   "dark":  dict(bg="0B0905", surface="110E08", card="16120A", elevated="211B10", overlay="2D2516",
                 border="FDE68A", subtle="3A3020", text="FFFBEB", text2="E0CFA6", muted="A8946A", disabled="4E4330",
                 primary="FACC15", hover="EAB308", plight="FEF9C3", pmuted="713F12", on="1A1300", shadow="FACC15"),
   "light": dict(bg="FFFDF5", surface="FEF8E7", card="FFFFFF", elevated="FBF0CF", overlay="F4E3B0",
                 border="241A00", subtle="E8D9A8", text="241A00", text2="4D3D12", muted="76662F", disabled="C2B58A",
                 primary="A16207", hover="854D0E", plight="FEF3C7", pmuted="FDE68A", on="FFFFFF", shadow="241A00")},
 "neon": {"name": "Neon Night", "blurb": "Hot pink on midnight indigo",
   "dark":  dict(bg="0C0618", surface="110A20", card="160E29", elevated="1F1637", overlay="2A1F47",
                 border="F5D0FE", subtle="2E2350", text="FDF4FF", text2="D2C0E8", muted="9A86B8", disabled="463A63",
                 primary="F472B6", hover="EC4899", plight="FCE7F3", pmuted="831843", on="1F0414", shadow="F472B6"),
   "light": dict(bg="FDF7FF", surface="F8EEFE", card="FFFFFF", elevated="F1E0FB", overlay="E6CCF6",
                 border="2A0B3D", subtle="DDC4EC", text="2A0B3D", text2="4E2A66", muted="77548F", disabled="C3A9D3",
                 primary="BE185D", hover="9D174D", plight="FCE7F3", pmuted="FBCFE8", on="FFFFFF", shadow="2A0B3D")},
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
