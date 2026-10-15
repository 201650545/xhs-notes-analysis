# -*- coding: utf-8 -*-
"""打印争议篇清单供呈报"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(BASE, "review_diff_batch.json"), encoding="utf-8"))
print("META:", json.dumps(d["meta"], ensure_ascii=False))
for i, x in enumerate(d["dispute"], 1):
    print("\n[%d] %s (%s)" % (i, x["title"], x["id"]))
    print("  一审%s：%s" % (x["first_verdict"], x["first_reason"]))
    print("  二审%s：%s" % (x["second_verdict"], x["second_reason"]))
