# -*- coding: utf-8 -*-
"""合并一审分组文件，校验146篇齐套，输出 first_review_all.json"""
import json, glob, os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(BASE, "first_review_[A-FD]*.json")))
# first_review_D1/D2 也要含入：pattern [A-FD]* 覆盖 A,B,C,D1,D2,E,F
all_items, seen = [], set()
dup = []
for f in files:
    items = json.load(open(f, encoding="utf-8"))
    print(os.path.basename(f), len(items))
    for x in items:
        if x["id"] in seen:
            dup.append(x["id"])
        seen.add(x["id"])
        all_items.append(x)

print("total", len(all_items), "unique", len(seen), "dup", dup)
c = Counter(x["verdict"] for x in all_items)
print("verdict分布", dict(c))
batch_ids = [x["id"] for x in json.load(open(os.path.join(BASE, "batch_ids_20261013.json"), encoding="utf-8"))]
missing = [i for i in batch_ids if i not in seen]
extra = [i for i in seen if i not in set(batch_ids)]
print("缺失", missing, "多余", extra)
json.dump(all_items, open(os.path.join(BASE, "first_review_all.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("输出 first_review_all.json")
