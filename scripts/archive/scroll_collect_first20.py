import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
# -*- coding: utf-8 -*-
"""重启后重跑：CDP物理滚轮采集最早20条。
虚拟列表会回收DOM，用merged累积；wheel响应超时忽略。"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"<PROJECT_DIR>\scripts")
from batch_final import cmd, ev, API, SESSION

BASE = r"<PROJECT_DIR>"
LIKED = "https://www.xiaohongshu.com/user/profile/<XHS_USER_ID>?tab=liked"
UID = get_cred("XHS_USER_ID", "<XHS_USER_ID>")

EXTRACT_JS = r"""
(() => {
  const uid = get_cred("XHS_USER_ID", "<XHS_USER_ID>");
  const items = [];
  document.querySelectorAll("section.note-item, div.note-item").forEach((c) => {
    const a = c.querySelector("a.cover") || c.querySelector("a");
    const href = a ? (a.getAttribute("href") || "") : "";
    let mid = "";
    const ps = (href.split("?")[0]).split("/");
    for (let i = ps.length - 1; i >= 0; i--) {
      if (/^[0-9a-f]{24}$/.test(ps[i]) && ps[i] !== uid) { mid = ps[i]; break; }
    }
    if (!mid) return;
    let full = href.indexOf("http") === 0 ? href : "https://www.xiaohongshu.com" + href;
    items.push({ id: mid, href: full,
                 title: (c.querySelector(".title, a.title")?.innerText || "").trim() });
  });
  const titles = items.map(x => x.title.slice(0, 10));
  return JSON.stringify({items, first: titles[0] || "", last: titles[titles.length-1] || ""});
})()
"""


def wheel(delta):
    body = json.dumps({"action": "cdp",
                       "args": {"method": "Input.dispatchMouseEvent",
                                "params": {"type": "mouseWheel", "x": 960, "y": 720,
                                           "deltaX": 0, "deltaY": delta}},
                       "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=6).read()
    except Exception:
        pass


def grab():
    return json.loads(ev(EXTRACT_JS) or '{"items":[],"first":"","last":""}')


targets = {x["id"]: x for x in
           json.load(open(BASE + r"\_first20_items.json", encoding="utf-8"))["items"]}

cmd("navigate", {"url": LIKED, "newTab": False})
time.sleep(9)

merged = {}
stale = 0
delta = 800
for page in range(120):
    d = grab()
    new = 0
    for it in d["items"]:
        if it["id"] not in merged:
            merged[it["id"]] = (it["href"], it["title"])
            new += 1
            if it["id"] in targets:
                print("  ★ #%02d %s（%d/20）"
                      % (targets[it["id"]]["seq"], it["title"][:22],
                         len(set(merged) & set(targets))), flush=True)

    hit = len(set(merged) & set(targets))
    print("[轮%3d] 累计 %4d（本轮+%d）| 目标 %d/20 | 视口尾:%s"
          % (page, len(merged), new, hit, d["last"][:14]), flush=True)

    if hit == len(targets):
        print(">>> 全部命中", flush=True)
        break

    if new == 0:
        stale += 1
        if stale == 4:
            delta = 1600  # 加大滚动量
        if stale >= 8:
            print(">>> 8轮无新增，判定到底", flush=True)
            break
    else:
        stale = 0
        delta = 800

    wheel(delta)
    time.sleep(2.8)

result, missing = [], []
for nid, x in targets.items():
    if nid in merged:
        y = dict(x)
        y["href"] = merged[nid][0]
        result.append(y)
    else:
        missing.append((x["seq"], x["title"][:24]))
result.sort(key=lambda z: z["seq"])
json.dump(dict(source="lark_first20_with_token", count=len(result), items=result),
          open(BASE + r"\_first20_items_tok.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n带token %d/20（累计加载 %d 条）-> _first20_items_tok.json"
      % (len(result), len(merged)))
for m in sorted(missing):
    print("  缺失:", m)