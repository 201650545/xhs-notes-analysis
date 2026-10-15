# -*- coding: utf-8 -*-
"""二审判决守望进程
用法：
  python scripts\\watch_verdict.py --batch <批次名> [--interval 300] [--max-minutes 120]

行为：
  每 --interval 秒扫一次下载目录，找固定名 verdict_<批次>_final*.json
  （Chrome 重复下载会带 " (1)" 后缀，也能识别，取最新的一个）。
  找到 → 校验 JSON → 移动（不是复制）到项目 _系统数据\\verdicts\\ → 打印汇总后退出（exit 0）。
  超时 --max-minutes 仍未出现 → 打印超时并退出（exit 2），即“自动解绑”。
  移动走原件，避免下次导出同名冲突与重复收取。
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

DL_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(PROJ_ROOT, "_系统数据", "verdicts")


def candidates(downloads, batch):
    pat = os.path.join(downloads, "verdict_" + batch + "_final*.json")
    files = [f for f in glob.glob(pat) if not f.endswith(".crdownload")]
    return sorted(files, key=os.path.getmtime, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--max-minutes", type=int, default=120)
    ap.add_argument("--downloads", default=DL_DIR)
    args = ap.parse_args()

    deadline = time.time() + args.max_minutes * 60
    os.makedirs(INBOX, exist_ok=True)
    print("[watch] 批次=%s  每%d秒扫一次  最长%d分钟  目录=%s"
          % (args.batch, args.interval, args.max_minutes, args.downloads), flush=True)

    while time.time() < deadline:
        files = candidates(args.downloads, args.batch)
        if files:
            src = files[0]
            try:
                with open(src, encoding="utf-8-sig") as f:
                    v = json.load(f)
                assert v.get("kind") == "second_review_verdict"
                assert v.get("batch") == args.batch
            except Exception as e:
                print("[watch] 发现文件但校验失败，等下一份：%s (%s)" % (os.path.basename(src), e), flush=True)
                time.sleep(args.interval)
                continue
            c = v.get("counts", {})
            dst = os.path.join(INBOX, "verdict_%s_final.json" % args.batch)
            if os.path.exists(dst):
                bak = dst + ".%d.bak" % int(time.time())
                os.rename(dst, bak)
                print("[watch] 旧判决已备份：%s" % os.path.basename(bak), flush=True)
            shutil.move(src, dst)
            print("[watch] FOUND 已收取 → %s" % dst, flush=True)
            print("[watch] 结果：共%d篇  留%d  删%d  待判%d  demo=%s"
                  % (v.get("total", -1), c.get("keep", 0), c.get("drop", 0),
                     c.get("pending", 0), v.get("demo", False)), flush=True)
            # 收到即自动分析：跑 apply_verdict 的 dry-run（只校验＋写预览，不碰数据），
            # 真删仍需他一个字确认——规范 §5 明令 dry-run→确认→apply。
            av = os.path.join(PROJ_ROOT, "scripts", "apply_verdict.py")
            if os.path.exists(av) and not v.get("demo"):
                p = subprocess.run([sys.executable, av, "--batch", args.batch],
                                   capture_output=True, text=True, encoding="utf-8")
                print("[watch] 自动分析（dry-run）退出码=%d" % p.returncode, flush=True)
                print((p.stdout or "") + (p.stderr or ""), flush=True)
            return 0
        time.sleep(args.interval)

    print("[watch] TIMEOUT %d分钟内未收到判决，守望自动解除" % args.max_minutes, flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
