import json, glob, sys, re
from urllib.parse import urlparse
base = sys.argv[1]
names = {"LA":"Louisiana","AR":"Arkansas","AL":"Alabama","TN":"Tennessee","MS":"Mississippi","NJ":"New Jersey","SC":"South Carolina","AZ":"Arizona","MO":"Missouri","NV":"Nevada","WV":"West Virginia","PR":"Puerto Rico","US":"Federal"}
rows, seen = [], set()
for f in sorted(glob.glob(base + "/research/group_*.json")):
    for r in json.load(open(f)):
        rid = re.sub(r"[^a-z0-9-]", "-", r["id"].lower())
        if rid in seen: rid += "-2"
        seen.add(rid)
        def c(x):
            s = x.get("name","")
            tags = [x.get("party","")] + (["inc."] if x.get("incumbent") else [])
            return f"{s} ({', '.join(t for t in tags if t)})"
        srcs = r.get("sources") or []
        src = srcs[0] if srcs else ""
        txt = lambda v: (v or "").replace("—", ", ").replace("–", "-")
        rows.append({
            "id": rid, "state": r["state"], "state_name": names.get(r["state"], r["state"]),
            "level": r.get("level",""), "office": txt(r.get("office")), "date": r.get("date","2026-11-03"),
            "candidates": txt("; ".join(c(x) for x in r.get("candidates", []))),
            "priority": r.get("priority","low"), "impact": txt(r.get("impact")),
            "status": r.get("status","upcoming"), "winner": txt(r.get("winner") or ""),
            "result_note": txt(r.get("result_note")), "source": src,
            "source_label": urlparse(src).netloc.replace("www.","") if src else "",
        })
json.dump(rows, open(base + "/races.json","w"), indent=1)
from collections import Counter
print(len(rows), Counter(r["state"] for r in rows), Counter(r["priority"] for r in rows))
