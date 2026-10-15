# -*- coding: utf-8 -*-
"""20条挂起移入pending（郭老师三审后决策：仅执行126篇）"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
HOLD = """6a615436000000000f030126 6a97b69c0000000026022166 6a9a972500000000120037ba
6a9aa56b000000002802fb2e 6aa10dd7000000002901a9e3 6aa93960000000001203d688
6aa975ec000000002b002588 6aaa56ff000000000b00ea14 6aad890e000000002902d656
6aadf8bb000000002b02732a 6aae5cbe000000002802ff7f 6ab2ad33000000001802e503
6abb11620000000015007d2c 6abb1ac0000000001801711b 6abb7bcc000000001c01ec86
6abb8fdd000000001c01f49c 6abbd8310000000001009493 6a36ae9d000000001003c562
6aa3c627000000002601b5b5 6abd234f000000000d00a675""".split()

vp = os.path.join(BASE, "verdicts", "verdict_20261013_final.json")
v = json.load(open(vp, encoding="utf-8"))
hold = [i for i in HOLD if i in v["keep"] or i in v["drop"]]
assert len(hold) == 20, len(hold)
v["keep"] = [i for i in v["keep"] if i not in hold]
v["drop"] = [i for i in v["drop"] if i not in hold]
v["pending"] = sorted(set(v.get("pending", [])) | set(hold))
v["hold_reason"] = "三件不齐挂起（13台账缺/7映射缺），郭老师20261013决策：仅执行126篇"
json.dump(v, open(vp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("执行集：留%d 删%d 挂起%d" % (len(v["keep"]), len(v["drop"]), len(v["pending"])))
