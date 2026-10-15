# -*- coding: utf-8 -*-
"""艾丽全量笔记抓取 I 期：她主页可见的 30 篇（约近 6 周日更），逐篇读正文存档。
手法：同 tab 逐个 navigate /explore/<id> + read_page（管线同款会话，不另开窗口）。
产物：D:\\Work\\小红书点赞分析\\_系统数据\\ela_notes\\<id>.txt（标题+正文原文，供方法论提炼）。
跑完自动关闭本任务标签页，不干扰每日管线。"""
import json, os, sys, time, urllib.request

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
OUT = r"<PROJECT_DIR>\_系统数据\ela_notes"
os.makedirs(OUT, exist_ok=True)
API = "http://127.0.0.1:10086/command"

def cmd(action, args):
    body = json.dumps({"action": action, "args": args, "session": "xhs-mgr"},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

def sweep():
    done, fail = 0, []
    for i, nid in enumerate(IDS):
        fp = os.path.join(OUT, nid + ".txt")
        if os.path.exists(fp) and os.path.getsize(fp) > 500:
            print("[%d/30] 跳过（已有） %s" % (i + 1, nid[:8]), flush=True)
            done += 1
            continue
        r = cmd("navigate", {"url": "https://www.xiaohongshu.com/explore/" + nid})
        if not r.get("ok"):
            fail.append((nid, "nav:" + str(r.get("error"))[:60]))
            continue
        time.sleep(9)
        txt = ""
        for _ in range(2):
            r2 = cmd("read_page", {})
            try:
                txt = str(r2.get("data", {}).get("text", "") or r2.get("data", ""))
            except Exception:
                txt = str(r2.get("data", ""))
            if len(txt) > 800:
                break
            time.sleep(5)
        if len(txt) < 800:
            fail.append((nid, "empty:%d" % len(txt)))
            continue
        with open(fp, "w", encoding="utf-8") as f:
            f.write("# 艾丽的无废话财经 · %s\n# https://www.xiaohongshu.com/explore/%s\n\n%s"
                    % (nid, nid, txt))
        done += 1
        print("[%d/30] ✓ %s (%d字)" % (i + 1, nid[:8], len(txt)), flush=True)
        time.sleep(2)
    print("完成：%d/30，失败 %d" % (done, len(fail)), flush=True)
    for nid, why in fail:
        print("  FAIL %s %s" % (nid[:8], why), flush=True)

if __name__ == "__main__":
    sweep()
