# -*- coding: utf-8 -*-
"""批量深度分析 batch_ids_20261013.json 里的 146 条笔记。
用法: python batch_batchids.py [--limit 146] [--offset 0]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_ORIG_ARGV = sys.argv[:]
sys.argv = [sys.argv[0], "1", "0"]
import batch_liked_100 as B
sys.argv = _ORIG_ARGV

OUT_DIR = r"D:\Work\小红书点赞分析\b_answers"
SRC = r"D:\Work\小红书点赞分析\_系统数据\batch_ids_20261013.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=146)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    import xhs_like_manager as M
    M.ensure_webbridge(wait=90)
    B.SESSION = "xhs"

    items = json.load(open(SRC, encoding="utf-8"))
    total = len(items)
    print(">>> batch_ids 共 %d 条" % total, flush=True)

    # 跳过已有
    todo = []
    for it in items:
        out_path = os.path.join(OUT_DIR, "%s.txt" % it["id"])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            continue
        todo.append(it)
    print("待分析：%d 篇" % len(todo), flush=True)

    batch = todo[args.offset:args.offset + args.limit]
    ok = skip_excl = fail = 0
    for idx, it in enumerate(batch):
        nid = it["id"]
        title = it.get("title", "") or nid
        href = "https://www.xiaohongshu.com/explore/%s" % nid
        out_path = os.path.join(OUT_DIR, "%s.txt" % nid)

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