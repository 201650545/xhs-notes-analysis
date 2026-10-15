# -*- coding: utf-8 -*-
"""最终采集：scrollTop + wheel 组合驱动虚拟列表，持续累积抓token链接。
页面当前已在第2页附近，不重载。"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\Work\小红书点赞分析\scripts")
from batch_final import ev, API, SESSION

BASE = r"D:\Work\小红书点赞分析"

EXTRACT_JS = r"""
(() => {
  const uid = "6292cc04000000002102272a";
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
  const ts = items.map(x => x.title);
  return JSON.stringify({items, first: ts[0] || "", last: ts[ts.length-1] || ""});
})()
"""

# 组合滚动：强设 user-page scrollTop + scroll 事件 + wheel 事件
ROLL_JS = r"""
(() => {
  const up = document.querySelector('.ai-mode.user-page');
  const before = up ? up.scrollTop : -1;
  if (up) {
    up.scrollTop = up.scrollTop + 3000;
    up.dispatchEvent(new Event('scroll', {bubbles: true}));
  }
  const el = document.elementFromPoint(960, 700) || document.body;
  el.dispatchEvent(new WheelEvent('wheel',
    {deltaY: 1500, bubbles: true, cancelable: true}));
  return JSON.stringify({before, after: up ? up.scrollTop : -1});
})()
"""


def cdp_wheel():
    body = json.dumps({"action": "cdp",
                       "args": {"method": "Input.dispatchMouseEvent",
                                "params": {"type": "mouseWheel", "x": 960, "y": 700,
                                           "deltaX": 0, "deltaY": 1500}},
                       "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass


def grab():
    return json.loads(ev(EXTRACT_JS) or '{"items":[],"first":"","last":""}')


targets = {x["id"]: x for x in
           json.load(open(BASE + r"\_first20_items.json", encoding="utf-8"))["items"]}

# 先用当前 DOM 初始化 merged
merged = {}
for it in grab()["items"]:
    merged[it["id"]] = (it["href"], it["title"])
print("起始已见 %d 条，目标 %d 条" % (len(merged), len(targets)), flush=True)

stale = 0
last_first = ""
for page in range(120):
    d = grab()
    new = 0
    for it in d["items"]:
        if it["id"] not in merged:
            merged[it["id"]] = (it["href"], it["title"])
            new += 1
            if it["id"] in targets:
                print("  ★ #%02d %s（%d/20）"
                      % (targets[it["id"]]["seq"], it["title"][:24],
                         len(set(merged) & set(targets))), flush=True)

    hit = len(set(merged) & set(targets))
    print("[轮%3d] 累计 %4d（+%d）| 目标 %d/20 | %s … %s"
          % (page, len(merged), new, hit, d["first"][:12], d["last"][:14]), flush=True)

    if hit == len(targets):
        print(">>> 全部命中", flush=True)
        break

    # 视口在移动或有新卡片 -> 健康；否则累计 stale
    moving = (new > 0) or (d["first"] != last_first)
    last_first = d["first"]
    if not moving:
        stale += 1
        if stale >= 10:
            print(">>> 10轮完全不动，判定到底", flush=True)
            break
    else:
        stale = 0

    ev(ROLL_JS)
    cdp_wheel()
    time.sleep(3)

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
print("\n带token %d/20（全程累计 %d 条）-> _first20_items_tok.json"
      % (len(result), len(merged)))
for m in sorted(missing):
    print("  缺失:", m)