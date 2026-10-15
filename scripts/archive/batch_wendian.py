# -*- coding: utf-8 -*-
"""小红书点赞笔记批量总结（首页问点点 + 回车发送），带断点续传与拒答重试。"""
import json
import os
import re
import sys
import time
import urllib.request

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
HOME = "https://www.xiaohongshu.com/explore"
ITEMS = r"D:\Work\小红书点赞分析\_liked_list_now.json"
OUT_DIR = r"D:/workbuddy 工作空间/点点分析结果/raw_20260923"
PROMPT = "请总结这个小红书笔记的内容，给出：1)内容概要 2)主题分类 3)关键信息点。链接：%s"

REFUSE = ["无法直接访问", "无法访问小红书", "暂时无法为您总结", "我目前无法", "请提供具体", "可以尝试以下方法"]
OK = ["内容概要", "主题分类", "关键信息点", "总结内容"]


def cmd(action, args=None, timeout=90):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError("%s -> %s" % (action, json.dumps(r, ensure_ascii=False)[:200]))
    return r.get("data", {})


def ev(code):
    return cmd("evaluate", {"code": code})["value"]


ENTER_JS = r"""
(() => {
  const ta = document.querySelector('#search-input-in-feeds');
  if (!ta) return 'no-input';
  ta.focus();
  const o = { key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true, composed:true };
  ['keydown','keypress','keyup'].forEach(t => ta.dispatchEvent(new KeyboardEvent(t, o)));
  return 'sent';
})()
"""

READ_JS = r"""
(() => {
  const ai = [...document.querySelectorAll('.ai-message')].filter(e => e.offsetParent);
  if (!ai.length) return JSON.stringify({state:'waiting'});
  const last = ai[ai.length - 1];
  return JSON.stringify({
    state: last.className.indexOf('finished') > -1 ? 'done' : 'streaming',
    text: last.innerText.trim()
  });
})()
"""

MODE_JS = r"""
(() => {
  const ta = document.querySelector('#search-input-in-feeds');
  return ta ? (ta.getAttribute('placeholder') || '') : 'none';
})()
"""


def quality(t):
    bad = sum(1 for k in REFUSE if k in t)
    good = sum(1 for k in OK if k in t)
    return good >= 2 and bad == 0 and len(t) > 150


def run_one(item):
    href = item["href"]
    cmd("navigate", {"url": HOME, "newTab": False})
    time.sleep(6.5)

    cmd("click", {"selector": "button.wendian-btn"})
    time.sleep(2.5)
    ph = ev(MODE_JS)
    if "？" not in ph and "?" not in ph:
        return None, "未进入点点模式(ph=%s)" % ph[:20]

    cmd("fill", {"selector": "#search-input-in-feeds", "value": PROMPT % href})
    time.sleep(0.8)
    ev(ENTER_JS)

    for i in range(16):
        time.sleep(3)
        try:
            d = json.loads(ev(READ_JS))
        except Exception:
            continue
        if d.get("state") == "done" and d.get("text"):
            return d["text"], "ok"
    return None, "超时无回答"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = json.load(open(ITEMS, encoding="utf-8"))["items"]
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(items)

    print(">>> 待处理 %d 条（序号 %d~%d）" % (end - start, start, end - 1), flush=True)
    ok_n = skip_n = fail_n = 0

    for i in range(start, end):
        it = items[i]
        path = os.path.join(OUT_DIR, "raw_%d_%s.txt" % (i, it["id"]))
        if os.path.exists(path):
            txt = open(path, encoding="utf-8").read()
            if quality(txt):
                skip_n += 1
                print("[%2d/%d] %s 跳过（已存在合格结果）" % (i, end - 1, it["id"]), flush=True)
                continue

        print("[%2d/%d] %s | %s" % (i, end - 1, it["id"], it["title"][:30]), flush=True)
        text, status = None, ""
        for attempt in (1, 2):
            try:
                text, status = run_one(it)
            except Exception as e:
                text, status = None, "异常:%s" % str(e)[:80]
            if text and quality(text):
                break
            if attempt == 1:
                print("     重试中(%s)..." % status, flush=True)
                time.sleep(3)

        if text and quality(text):
            with open(path, "w", encoding="utf-8") as f:
                f.write("【标题】%s\n【作者】%s\n【链接】%s\n【点赞】%s\n\n【点点回复】\n%s\n"
                        % (it["title"], it["author"], it["href"], it["like"], text))
            ok_n += 1
            print("     ✅ %d 字" % len(text), flush=True)
        else:
            fail_n += 1
            print("     ❌ %s" % status, flush=True)

    print("\n>>> 完成：成功 %d | 跳过 %d | 失败 %d" % (ok_n, skip_n, fail_n), flush=True)
    print(">>> 输出目录:", OUT_DIR, flush=True)


if __name__ == "__main__":
    main()