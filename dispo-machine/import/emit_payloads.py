"""Emit one GHL create-contact body per buyer, straight from the same plan the
review tab was built from. Written to a file so the push is replayable and so
the exact payload that went to GHL is auditable afterwards."""
import json, os, sys, runpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_import as B

# Reuse the build without its push/CLI: monkeypatch the sheet writer away.
rows_holder = []
_orig_write = B.write_review
def capture(svc, out):
    rows_holder.append(out)
    _orig_write(svc, out)
B.write_review = capture
sys.argv = ["build_import.py"]
B.main()

out = rows_holder[0]
todo = [r for r in out if r["action"] == "CREATE"]

payloads = []
for r in todo:
    body = {"locationId": B.LOCATION, "phone": r["phone"],
            "firstName": r["first"], "lastName": r["last"],
            "source": "Master buyer sheet import",
            "customFields": B.payload_fields(r)}
    if r["email"]:
        body["email"] = r["email"]
    if r["company"]:
        body["companyName"] = r["company"]
    payloads.append({"row": r["row"], "name": (r["first"] + " " + r["last"]).strip(),
                     "phone": r["phone"], "body": body})

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payloads.json")
json.dump(payloads, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("\n%d payloads -> %s" % (len(payloads), path))
