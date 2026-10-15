# -*- coding: utf-8 -*-
"""核查20条三件不齐：台账/映射/全文/新任务records四处状态"""
import json, os
BASE = r"<PROJECT_DIR>"
ledger = json.load(open(os.path.join(BASE, "_系统数据", "_routing.json"), encoding="utf-8"))
mapping = json.load(open(os.path.join(BASE, "_系统数据", "_lark_map.json"), encoding="utf-8"))
ANS = os.path.join(BASE, "b_answers")
newt = json.load(open(os.path.join(BASE, "_系统数据", "_new_tasks.json"), encoding="utf-8"))
rec_ids = {r["id"]: (r.get("title"), r.get("status")) for r in newt.get("records", [])}

ids = """6a615436000000000f030126 6a97b69c0000000026022166 6a9a972500000000120037ba
6a9aa56b000000002802fb2e 6aa10dd7000000002901a9e3 6aa93960000000001203d688
6aa975ec000000002b002588 6aaa56ff000000000b00ea14 6aad890e000000002902d656
6aadf8bb000000002b02732a 6aae5cbe000000002802ff7f 6ab2ad33000000001802e503
6abb11620000000015007d2c 6abb1ac0000000001801711b 6abb7bcc000000001c01ec86
6abb8fdd000000001c01f49c 6abbd8310000000001009493 6a36ae9d000000001003c562
6aa3c627000000002601b5b5 6abd234f000000000d00a675""".split()
for i in ids:
    print(i, "|台账", "有" if i in ledger else "无",
          "|映射", "有" if i in mapping else "无",
          "|全文", "有" if os.path.exists(os.path.join(ANS, i + ".txt")) else "无",
          "|新任务", rec_ids.get(i, "无"))
