# -*- coding: utf-8 -*-
"""诊断补跑失败：打印每篇 err/raw 全文"""
import json, glob, os
BASE = os.path.dirname(os.path.abspath(__file__))
fs = sorted(glob.glob(os.path.join(BASE, "verdicts_gateway_*.json")))
p = fs[-1]
print("文件:", os.path.basename(p))
d = json.load(open(p, encoding="utf-8"))
for x in d.get("results", []):
    print("=" * 60)
    print(x.get("id"), "->", x.get("err"))
    print("RAW:", repr(x.get("raw", ""))[:2000])
