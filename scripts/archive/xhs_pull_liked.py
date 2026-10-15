import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
# -*- coding: utf-8 -*-
import json, sys, time, urllib.request

API = "http://127.0.0.1:10086/command"

def evaluate(code):
    body = json.dumps({"action": "evaluate", "args": {"code": code}}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    if not resp.get("ok"):
        raise RuntimeError(json.dumps(resp.get("error")))
    return resp["data"]["value"]

JS = r"""
(() => {
  const uid = get_cred("XHS_USER_ID", "<XHS_USER_ID>");
  const items = [];
  const cards = document.querySelectorAll("section.note-item, div.note-item");
  cards.forEach((c) => {
    const a = c.querySelector("a.cover") || c.querySelector("a");
    const href = a ? (a.getAttribute("href") || "") : "";
    // note_id = path 中位于 uid 之后的 hex 段，取最后一节路径段中 24 位 hex
    let mid = "";
    const pathSeg = (href.split("?")[0]).split("/");
    for (let i = pathSeg.length - 1; i >= 0; i--) {
      const s = pathSeg[i];
      if (/^[0-9a-f]{24}$/.test(s) && s !== uid) { mid = s; break; }
    }
    if (!mid) return;
    let full = href;
    if (href.indexOf("http") !== 0) full = "https://www.xiaohongshu.com" + href;
    const title = (c.querySelector(".title, a.title")?.innerText || "").trim();
    const author = (c.querySelector(".author, .name, .author-wrapper .name")?.innerText || "").trim();
    const like = (c.querySelector(".like-wrapper .count, .count, .like")?.innerText || "").trim();
    const t = c.innerText;
    const type = t.indexOf("视频") > -1 ? "视频" : (t.indexOf("笔记") > -1 ? "笔记" : "");
    items.push({ id: mid, href: full, title, author, like, type });
  });
  return JSON.stringify({ uid, count: items.length, items, url: location.href });
})()
"""

out = evaluate(JS)
with open(r"D:\workbuddy 工作空间\_liked_list_latest.json", "w", encoding="utf-8") as f:
    f.write(out)
print(out[:3000])