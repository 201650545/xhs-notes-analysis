# -*- coding: utf-8 -*-
"""合并三轮二审：主轮fast + 补轮free-flash + 终补2篇短理由 → final"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
main = json.load(open(os.path.join(BASE, "verdicts_gateway_20261013_170855.json"), encoding="utf-8"))
res = {x["id"]: x for x in main["results"]}
n1 = sum(1 for x in res.values() if x.get("verdict") in ("keep", "drop"))
sup = json.load(open(os.path.join(BASE, "verdicts_gateway_20261013_181645.json"), encoding="utf-8"))
for x in sup["results"]:
    if x.get("verdict") in ("keep", "drop"):
        res[x["id"]] = x
patch = json.load(open(os.path.join(BASE, "second_patch.json"), encoding="utf-8"))
for x in patch:
    if x.get("verdict") in ("keep", "drop"):
        res[x["id"]] = x
ok = sum(1 for x in res.values() if x.get("verdict") in ("keep", "drop"))
bad = {k: v for k, v in res.items() if v.get("verdict") not in ("keep", "drop")}
print("主轮有效%d 终版有效%d 失败%d" % (n1, ok, len(bad)), list(bad))
final = {"model": "fast+free-flash(11篇)+short补采(2篇)", "ts": "20261013_final",
         "results": [res[k] for k in sorted(res)]}
json.dump(final, open(os.path.join(BASE, "verdicts_gateway_20261013_final.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("输出 verdicts_gateway_20261013_final.json，共%d篇" % len(final["results"]))
