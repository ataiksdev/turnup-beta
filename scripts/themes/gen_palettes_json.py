import json, sys
sys.path.insert(0, sys.argv[1]); from palettes import P, cr
VARS = [("bg","--bg"),("surface","--bg-surface"),("card","--bg-card"),("elevated","--bg-elevated"),
        ("overlay","--bg-overlay"),("border","--border"),("subtle","--border-subtle"),("border","--border-strong"),
        ("text","--text"),("text2","--text-secondary"),("muted","--text-muted"),("disabled","--text-disabled"),
        ("primary","--primary"),("hover","--primary-hover"),("plight","--primary-light"),("pmuted","--primary-muted"),
        ("on","--on-primary"),("shadow","--shadow-color")]
rgb = lambda h: f"{int(h[0:2],16)} {int(h[2:4],16)} {int(h[4:6],16)}"
out = {pid: {"name": p["name"], "blurb": p["blurb"],
             "modes": {m: {css: rgb(p[m][k]) for k, css in VARS} for m in ("dark", "light")},
             "swatch": {m: "#" + p[m]["primary"] for m in ("dark", "light")},
             "chrome": {m: "#" + p[m]["bg"] for m in ("dark", "light")}}
       for pid, p in P.items()}
print(json.dumps(out, indent=2))
