# -*- coding: utf-8 -*-
"""对齐器：网关二审 verdict × 你的标准答案 → 一致/冲突表。
用法：python merge_verdicts.py _系统数据/verdicts_gateway_<ts>.json"""
import json, os, sys

BASE = r"D:\Work\小红书点赞分析"
gw = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "", encoding="utf-8")) \
    if len(sys.argv) > 1 else None

# 默认取最新一份
if not gw:
    import glob
    files = sorted(glob.glob(os.path.join(BASE, "_系统数据", "verdicts_gateway_*.json")))
    gw = json.load(open(files[-1], encoding="utf-8"))
    print("用最新:", files[-1])

truth = {}   # id -> (verdict, 原话)
for ln in open(os.path.join(BASE, "_系统数据", "text_review_verdicts.jsonl"), encoding="utf-8"):
    ln = ln.strip()
    if not ln:
        continue
    for it in json.loads(ln).get("items", []):
        if it.get("id") and it.get("你"):
            truth[it["id"]] = (it["你"], it["原话"], it["title"])

agree = conflict = err = 0
print("\n%-26s %-8s %-8s %s" % ("笔记", "你", "网关AI", "网关理由"))
print("-" * 100)
for r in gw["results"]:
    nid = r["id"]
    if nid not in truth:
        print("%-26s %-8s %-8s %s" % (nid[:8], "(你未判)", r.get("verdict") or "ERR", r.get("reason", "")[:40]))
        err += 1
        continue
    you, quote, title = truth[nid]
    ai = r.get("verdict")
    mark = "✓" if ai == you else "✗ 冲突"
    if ai == you:
        agree += 1
    else:
        conflict += 1
    print("%-26s %-8s %-8s %s  %s" % (title[:24], you, ai or "ERR", (r.get("reason") or "")[:36], mark))

total = agree + conflict
print("-" * 100)
print("一致 %d / 冲突 %d / 你未判 %d → 与你的口味一致率 %s" % (
    agree, conflict, err, "%.0f%%" % (100.0 * agree / total) if total else "—"))
if conflict:
    print("\n冲突篇（这些就是以后会自动推给你三审的）：")
    for r in gw["results"]:
        if r["id"] in truth and r.get("verdict") != truth[r["id"]][0]:
            print("  · %s" % truth[r["id"]][2][:30])
