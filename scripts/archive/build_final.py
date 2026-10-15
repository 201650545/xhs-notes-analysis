# -*- coding: utf-8 -*-
"""由双盲比对 + 三审判决生成执行批次：
输出 review_batch_20261013.tsv + verdicts/verdict_20261013_final.json
三审（郭老师）：争议28篇中第7(6aaa9317)、第8(6ab4e612)留，其余按一审。
"""
import json, os, csv

BASE = os.path.dirname(os.path.abspath(__file__))
BATCH = "20261013"

first = {x["id"]: x for x in json.load(open(os.path.join(BASE, "first_review_all.json"), encoding="utf-8"))}
diff = json.load(open(os.path.join(BASE, "review_diff_batch.json"), encoding="utf-8"))
sec = {x["id"]: x for x in json.load(
    open(os.path.join(BASE, "verdicts_gateway_20261013_final.json"), encoding="utf-8"))["results"]}

# 旧批次取 category
oldcat = {}
with open(os.path.join(BASE, "review_batch_20261010.tsv"), encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        oldcat[r["id"]] = r.get("category", "")

# 三审终判：争议篇 id -> keep/drop（默认一审 verdict）
third_keep = {"6aaa93170000000026022713", "6ab4e612000000001402e469"}  # 第7、第8
dispute_ids = {x["id"] for x in diff["dispute"]}
final, notes = {}, {}
for nid, f in first.items():
    if nid in dispute_ids:
        v = "keep" if (f["verdict"] == "keep" or nid in third_keep) else "drop"
        # 第8是相对一审的改判
        tag = "三审改判留" if (nid in third_keep and f["verdict"] == "drop") else "三审按一审" if nid not in third_keep else "三审确认留"
        notes[nid] = tag
    else:
        v = f["verdict"]
        notes[nid] = "双盲一致"
    final[nid] = v

keep = sorted(k for k, v in final.items() if v == "keep")
drop = sorted(k for k, v in final.items() if v == "drop")
assert len(keep) + len(drop) == 146, (len(keep), len(drop))
print("终判：留%d 删%d" % (len(keep), len(drop)))

# TSV（沿用旧列格式）
cols = ["id", "title", "category", "suggestion", "reason", "what", "use", "next", "cost", "fulltext"]
with open(os.path.join(BASE, "review_batch_%s.tsv" % BATCH), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
    w.writeheader()
    for nid in sorted(first):
        f1, s1 = first[nid], sec[nid]
        tag = "留" if final[nid] == "keep" else "删"
        reason = "【双盲终判·%s｜%s】一审%s：%s｜二审%s：%s" % (
            tag, notes[nid], f1["verdict"], f1["reason"], s1["verdict"], s1.get("reason", ""))
        if nid == "6ac0e605000000001301b619":
            reason += "｜人物注记：艾丽的无废话财经为已登记保留信源，另抓全量提炼，单篇删"
        w.writerow({"id": nid, "title": f1["title"], "category": oldcat.get(nid, ""),
                    "suggestion": final[nid], "reason": reason,
                    "what": f1.get("what", ""), "use": f1.get("use", ""),
                    "next": "", "cost": f1.get("pitfall", ""),
                    "fulltext": r"<PROJECT_DIR>\b_answers\%s.txt" % nid})

vp = os.path.join(BASE, "verdicts", "verdict_%s_final.json" % BATCH)
os.makedirs(os.path.dirname(vp), exist_ok=True)
import time
json.dump({"kind": "second_review_verdict", "batch": BATCH, "demo": False,
           "exported_at": time.strftime("%Y-%m-%d %H:%M"),
           "source": "双盲一审(Muse)+二审(网关fast/free-flash)+三审(郭老师)",
           "keep": keep, "drop": drop, "pending": []},
          open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("输出 review_batch_%s.tsv + verdicts/verdict_%s_final.json" % (BATCH, BATCH))
