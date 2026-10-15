# -*- coding: utf-8 -*-
"""艾丽笔记 v3 分析驱动（管线同款：点点卡片＋分类提示词，防风控节奏）。
用法：
  python ela_analyze.py --test 6acadfa0000000001203dfd8   # 单发测试
  python ela_analyze.py --all                             # 30 篇后台跑（断点续传）
输出：_系统数据/ela_notes/<id>.txt（v3 标记头）
"""
import datetime
import json
import os
import sys
import time

BASE = r"<PROJECT_DIR>"
sys.path.insert(0, os.path.join(BASE, "scripts"))
os.chdir(os.path.join(BASE, "scripts"))

import batch_final

IDS = [
    "6acadfa0000000001203dfd8", "6ac8a6520000000018038e7d", "6ac77b29000000001500aff6",
    "6ac47eb9000000001802cb73", "6ac3390a000000001a023612", "6ac0e605000000001301b619",
    "6ac089a0000000001301a495", "6abdffdd000000001500f7a0", "6abc7deb000000001802c9d8",
    "6ab8c6ee000000001b02c69b", "6ab76b90000000001500e898", "6ab6499e000000001b02fed6",
    "6ab5f61d000000001c00e0f9", "6ab3d998000000001a02922e", "6ab0a324000000001202550c",
    "6aaf7ca80000000012034c66", "6aacba78000000002900f770", "6aab3971000000001103bbf7",
    "6aa90e4f000000001103a683", "6aa7a0c9000000002900f076", "6aa3a7c8000000002700ab11",
    "6aa13c58000000001203c240", "6a9f99f40000000028000ac9", "6a9e788c00000000280344ab",
    "6a9cbc7f0000000012034ec1", "6a9bfaf800000000280020e2", "6a9b8c3e000000002700a9a7",
    "6a968f86000000001200227a", "6a952a30000000002603769e", "6a94b3190000000024005e5a",
]
OUT = os.path.join(BASE, "_系统数据", "ela_notes")
os.makedirs(OUT, exist_ok=True)

LOG = os.path.join(BASE, "logs", "ela_analyze_%s.log" % datetime.date.today().isoformat())

def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def one(nid):
    fp = os.path.join(OUT, "%s.txt" % nid)
    if os.path.exists(fp):
        try:
            head = open(fp, encoding="utf-8").read(200)
            if "v3" in head and len(open(fp, encoding="utf-8").read()) > 500:
                log("跳过（已有） %s" % nid[:8])
                return "skipped"
        except Exception:
            pass
    # 他点赞过的已有管线 v3 全文在 b_answers：直接复用，不重复烧点点
    src = os.path.join(BASE, "b_answers", "%s.txt" % nid)
    if os.path.exists(src) and os.path.getsize(src) > 500:
        with open(src, encoding="utf-8") as f:
            body = f.read()
        with open(fp, "w", encoding="utf-8") as f:
            f.write(body if body.startswith("# v3") else
                    "# v3-ela（复用管线分析）\n" + body)
        log("复用管线已有 %s" % nid[:8])
        return "reused"
    href = "https://www.xiaohongshu.com/explore/%s" % nid
    log("分析中：%s" % nid[:8])
    try:
        ans = batch_final.run_one(href, batch_final.PROMPTS["C方法论"])
    except Exception as e:
        log("  run_one 异常 %s：%s" % (nid[:8], str(e)[:120]))
        return "error"
    if ans and batch_final.quality(ans):
        with open(fp, "w", encoding="utf-8") as f:
            f.write("# v3-ela\n# https://www.xiaohongshu.com/explore/%s\n\n%s" % (nid, ans))
        log("  完成 ✓ (%d 字)" % len(ans))
        return "ok"
    log("  失败/低质 %s" % nid[:8])
    return "fail"

def main():
    if "--test" in sys.argv:
        nid = sys.argv[sys.argv.index("--test") + 1]
        log("=== 单发测试 %s ===" % nid[:8])
        print("RESULT:", one(nid))
        return
    ok = skip = fail = err = reused = 0
    for i, nid in enumerate(IDS):
        r = one(nid)
        ok += (r == "ok"); skip += (r == "skipped"); reused += (r == "reused")
        fail += (r == "fail"); err += (r == "error")
        time.sleep(20)   # 管线同款节奏余量（防风控）：每篇之间歇 20s
        if (i + 1) % 10 == 0:
            log("进度 %d/30（ok=%d 失败=%d）" % (i + 1, ok, fail + err))
    log("结束：ok=%d 跳过=%d 复用=%d 失败=%d 异常=%d" % (ok, skip, reused, fail, err))

if __name__ == "__main__":
    main()
