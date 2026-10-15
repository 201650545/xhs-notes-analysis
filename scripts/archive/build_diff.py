# -*- coding: utf-8 -*-
"""双盲比对：一审(first_review_all.json) vs 二审(最新verdicts_gateway_*.json)
输出 _系统数据/review_diff_batch.jsonMPS200PPPDNWKHNJQUSU
用法: python build_diff.py [--second <网关结果json路径>]
"""
import json, glob, os, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def latest_second():
    fs = sorted(glob.glob(os.path.join(BASE, "verdicts_gateway_*.json")))
    if not fs:
        raise SystemExit("无二审结果文件")
    return fs[-1]

sec_path = sys.argv[sys.argv.index("--second") + 1] if "--second" in sys.argv else latest_second()
first = {x["id"]: x for x in json.load(open(os.path.join(BASE, "first_review_all.json"), encoding="utf-8"))}
sec_raw = json.load(open(sec_path, encoding="utf-8"))
sec = {x["id"]: x for x in sec_raw.get("results", [])}

agree_keep, agree_drop, dispute, missing, errors = [], [], [], [], []
for nid, f in first.items():
    s = sec.get(nid)
    if s is None:
        missing.append(nid)
        continue
    if s.get("verdict") not in ("keep", "drop"):
        errors.append({"id": nid, "err": s.get("err", "unknown"), "raw": str(s.get("raw", ""))[:150]})
        continue
    rec = {"id": nid, "title": f["title"], "what": f.get("what", ""),
           "first_verdict": f["verdict"], "first_reason": f["reason"],
           "second_verdict": s["verdict"], "second_reason": s.get("reason", "")}
    if f["verdict"] == s["verdict"] == "keep":
        agree_keep.append(rec)
    elif f["verdict"] == s["verdict"] == "drop":
        agree_drop.append(rec)
    else:
        dispute.append(rec)

out = {
    "meta": {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
             "batch": "20261013_146", "total": len(first),
             "second_file": os.path.basename(sec_path), "second_model": sec_raw.get("model", ""),
             "agree_keep": len(agree_keep), "agree_drop": len(agree_drop),
             "dispute": len(dispute), "second_missing": len(missing), "second_errors": len(errors)},
    "agree_keep": agree_keep, "agree_drop": agree_drop, "dispute": dispute,
    "second_missing": missing, "second_errors": errors,
}
p = os.path.join(BASE, "review_diff_batch.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("total=%d keep=%d drop=%d dispute=%d missing=%d errors=%d" % (
    len(first), len(agree_keep), len(agree_drop), len(dispute), len(missing), len(errors)))
print("输出", p)
