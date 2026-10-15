# -*- coding: utf-8 -*-
"""一次性/定时：拉取全部点赞 → 取消所有已在 b_answers 有分析的笔记。
断点续传：读取 _unlike_progress.json 的 cancelled 列表，跳过已取消的。
用法: python unlike_analyzed.py [--limit 400] [--delay 5.0]
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xhs_like_manager as M

BASE = M.BASE_DIR
ANSWER_DIR = os.path.join(BASE, "b_answers")
PROGRESS_FILE = M.PROGRESS_FILE


def load_cancelled():
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            return set(json.load(f).get("cancelled", []))
    except Exception:
        return set()


def save_cancelled(cancelled):
    prog = {}
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            prog = json.load(f)
    except Exception:
        pass
    prog["cancelled"] = sorted(cancelled)
    prog["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    try:
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(prog, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存进度失败: %s" % str(e)[:100], flush=True)


def build_analyzed_set():
    ids = set()
    if not os.path.isdir(ANSWER_DIR):
        return ids
    for f in os.listdir(ANSWER_DIR):
        if f.endswith(".txt") and len(f) >= 20:
            nid = f[:-4]
            if len(nid) >= 16:
                ids.add(nid)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400, help="拉取点赞上限")
    ap.add_argument("--session", default="xhs-mgr")
    ap.add_argument("--delay", type=float, default=5.0, help="取消点赞间隔秒")
    args = ap.parse_args()

    M.ensure_webbridge(wait=90)

    xhs = M.XHS(args.session)
    for i in range(3):
        if xhs.bootstrap():
            break
        print("引导失败，重试 %d/3 ..." % (i + 1), flush=True)
        time.sleep(20)

    # 全量拉取
    print("拉取点赞列表 ...", flush=True)
    items = []
    cursor = ""
    for _ in range(20):
        r = xhs.fetch_chunk(cursor, pages=M.PAGES_PER_CHUNK)
        if not r.get("ok"):
            print("拉取失败: %s" % str(r)[:200], flush=True)
            break
        items.extend(r["notes"])
        print("  已拉取 %d 条, hasMore=%s" % (len(items), r.get("hasMore")), flush=True)
        if not r.get("hasMore"):
            break
        cursor = r.get("cursor", "")
        if len(items) >= args.limit:
            break
        time.sleep(1)

    print("拉取完成，共 %d 条" % len(items), flush=True)

    analyzed = build_analyzed_set()
    cancelled = load_cancelled()
    print("b_answers 已分析 ID: %d | 已取消记录: %d" % (len(analyzed), len(cancelled)), flush=True)

    # 匹配：当前点赞里已分析、且还没取消的
    to_unlike = [it for it in items if it["id"] in analyzed and it["id"] not in cancelled]
    print("待取消（已分析、未取消）: %d 篇" % len(to_unlike), flush=True)

    if not to_unlike:
        print("没有需要取消的", flush=True)
        return

    done = fail_streak = 0
    for it in to_unlike:
        nid = it["id"]
        r = xhs.unlike(nid)
        if r.get("ok"):
            done += 1
            fail_streak = 0
            cancelled.add(nid)
            save_cancelled(cancelled)
            print("  取消 ✓ [%d/%d] %s %s" % (done, len(to_unlike), nid, it.get("title", "")[:24]), flush=True)
            time.sleep(random.uniform(args.delay * 0.8, args.delay * 1.2))
        else:
            fail_streak += 1
            print("  取消失败 %s: %s" % (nid, r.get("msg") or r.get("raw") or "?"), flush=True)
            if fail_streak >= 5:
                print("连续失败 5 次，终止（可能触发风控），剩余 %d 篇待下次重试"
                      % (len(to_unlike) - done), flush=True)
                break
            time.sleep(5)

    print("\n>>> 完成：成功取消 %d / %d（已取消记录 %d）" % (done, len(to_unlike), len(cancelled)), flush=True)


if __name__ == "__main__":
    main()