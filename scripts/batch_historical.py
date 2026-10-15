# -*- coding: utf-8 -*-
"""批量深度分析历史 raw_* 里只有简版分析的笔记。
输入：扫描 D:\workbuddy 工作空间\点点分析结果\ 下所有 raw_*.txt
跳过：已在 b_answers 存在的、做菜/影视解说类、文件名无法提取 ID 的
用法: python batch_historical.py [--limit 100] [--offset 0]
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 先把原始参数存起来（batch_liked_100 import 时会改 sys.argv）
_ORIG_ARGV = sys.argv[:]
# batch_liked_100 会在 import 时用 sys.argv[1:3] 作为 LIMIT/OFFSET，先给它安全值
sys.argv = [sys.argv[0], "1", "0"]
import batch_liked_100 as B  # 复用 run_one / quality / excluded / cmd / ev 等
sys.argv = _ORIG_ARGV

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
OUT_DIR = r"D:\Work\小红书点赞分析\b_answers"
HIST_DIRS = [
    r"D:\workbuddy 工作空间\点点分析结果",
]
REFUSE = B.REFUSE
KW_EXCLUDE = B.KW_EXCLUDE


def extract_nid(filename):
    """从文件名提取 20-26 位 hex 笔记 ID。"""
    m = re.search(r'([0-9a-f]{20,26})', os.path.basename(filename))
    if m:
        return m.group(1)
    return None


def scan_historical():
    """扫描所有历史 raw_* 文件，返回 [{id, title_hint, path}]"""
    out = []
    seen = set()
    for d in HIST_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if not fn.lower().endswith(".txt"):
                    continue
                nid = extract_nid(fn)
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                out.append({
                    "id": nid,
                    "path": os.path.join(root, fn),
                    # 从文件名里尝试提取标题 hint（raw_N_{id} 格式无标题）
                })
    return out


def extract_title_from_file(path):
    """从历史文件内容里尝试提取笔记标题。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = f.read(3000)
        m = re.search(r'标题为[《"“\']?([^》"”\']{2,40})[》"”\']', head)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--session", default=SESSION)
    args = ap.parse_args()

    # 确保 webbridge 就绪
    import xhs_like_manager as M
    M.ensure_webbridge(wait=90)
    B.SESSION = args.session

    items = scan_historical()
    total = len(items)
    print(">>> 历史文件发现 %d 篇候选（去重后）" % total, flush=True)

    # 跳过已在 b_answers 的
    todo = []
    for it in items:
        out_path = os.path.join(OUT_DIR, "%s.txt" % it["id"])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            continue
        todo.append(it)

    print("待补深度分析：%d 篇" % len(todo), flush=True)
    if args.offset >= len(todo):
        print("offset 超出范围", flush=True)
        return
    batch = todo[args.offset:args.offset + args.limit]
    print("本次跑：%d 篇（offset=%d, limit=%d）" % (len(batch), args.offset, args.limit), flush=True)

    ok = skip_excl = fail = 0
    for idx, it in enumerate(batch):
        nid = it["id"]
        title = extract_title_from_file(it["path"]) or nid
        href = "https://www.xiaohongshu.com/explore/%s" % nid
        out_path = os.path.join(OUT_DIR, "%s.txt" % nid)

        # 跳过做菜/影视解说
        if B.excluded(title):
            skip_excl += 1
            print("[%d] ⊘ 跳过(做菜/影视) %s" % (idx + args.offset, title[:30]), flush=True)
            continue

        print("[%d] %s" % (idx + args.offset, title[:34]), flush=True)
        prompt = B.PROMPT % href
        text = None
        for attempt in (1, 2):
            try:
                text = B.run_one(href, prompt)
            except Exception as e:
                print("     异常: %s" % str(e)[:80], flush=True)
                text = None
            if text and B.quality(text):
                break
            print("     重试(attempt %d, 文本长度=%s)" % (attempt, len(text) if text else 0), flush=True)
            time.sleep(3)

        if text and B.quality(text):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("【标题】%s\n【链接】%s\n\n【点点回复】\n%s\n" % (title, href, text))
            ok += 1
            print("     ✅ %d 字" % len(text), flush=True)
        else:
            fail += 1
            print("     ❌ 失败", flush=True)
        time.sleep(2)

    print("\n>>> 完成：成功 %d | 跳过(做菜/影视) %d | 失败 %d" % (ok, skip_excl, fail), flush=True)


if __name__ == "__main__":
    main()