import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
# -*- coding: utf-8 -*-
"""统计小红书账号全部点赞历史（视频/笔记分类计数）。

关键修正：
- 每轮都用 OS 级 mouse_event 滚轮（已验证唯一有效方式），JS/CDP wheel 均失效
- force_foreground 每轮确保 Chrome 在前
- 连续 8 轮无新增才停（容纳虚拟列表懒加载）
- 类型识别：卡片内 <video> 标签 / .play-duration / .duration / 文字"视频" → 视频；其余 → 笔记
"""
import json
import time
import ctypes
import urllib.request
from ctypes import wintypes

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
UID = get_cred("XHS_USER_ID", "<XHS_USER_ID>")
LIKED_URL = "https://www.xiaohongshu.com/user/profile/%s?tab=liked" % UID
OUT = r"<PROJECT_DIR>\_系统数据\_liked_all_full.json"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()


def cmd(action, args=None, timeout=60):
    payload = {"action": action, "args": args or {}, "session": SESSION}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return resp


def ev(code, timeout=60):
    r = cmd("evaluate", {"code": code}, timeout=timeout)
    if r.get("ok"):
        return r.get("data", {}).get("value", "")
    return ""


def find_chrome_hwnd():
    """枚举所有 Chrome 主窗口（类名 Chrome_WidgetWin_1），返回可见且有标题的列表。"""
    found = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(wintypes.HWND), ctypes.POINTER(wintypes.LPARAM))
    GetClassName = user32.GetClassNameW
    buf_cls = ctypes.create_unicode_buffer(256)

    def proc(hwnd, lp):
        if user32.IsWindowVisible(hwnd):
            GetClassName(hwnd, buf_cls, 256)
            cls = buf_cls.value
            if cls == "Chrome_WidgetWin_1":
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf_t = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf_t, length + 1)
                    hwnd_val = ctypes.cast(hwnd, ctypes.POINTER(ctypes.c_void_p)).contents.value
                    found.append((hwnd_val, buf_t.value))
        return True

    user32.EnumWindows(EnumWindowsProc(proc), 0)
    if not found:
        print("    [find] 未找到 Chrome 窗口")
        return None
    print(f"    [find] Chrome 窗口 {len(found)} 个: {[(h, t[:20]) for h, t in found]}")
    # 优先返回标题含 小红书/xiaohongshu 的；否则返回最后一个
    for h, t in found:
        if '小红书' in t or 'xiaohongshu' in t.lower() or '点赞' in t or 'profile' in t.lower():
            return h
    return found[-1][0]


def force_foreground(h):
    fg = user32.GetForegroundWindow()
    cur_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    tgt_tid = user32.GetWindowThreadProcessId(h, None)
    if fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if tgt_tid != cur_tid and tgt_tid != fg_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, True)
    user32.ShowWindow(h, 9)
    user32.SetForegroundWindow(h)
    user32.BringWindowToTop(h)
    if fg_tid != cur_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if tgt_tid != cur_tid and tgt_tid != fg_tid:
        user32.AttachThreadInput(cur_tid, tgt_tid, False)
    time.sleep(0.6)
    return user32.GetForegroundWindow() == h


def os_wheel(delta=-120, x=1000, y=700, n=5):
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    for _ in range(n):
        user32.mouse_event(0x0800, 0, 0, delta, 0)
        time.sleep(0.2)


EXTRACT_JS = r"""
(() => {
  const uid = get_cred("XHS_USER_ID", "<XHS_USER_ID>");
  const items = [];
  const cards = document.querySelectorAll("section.note-item, div.note-item");
  cards.forEach((c) => {
    const a = c.querySelector("a.cover") || c.querySelector("a");
    const href = a ? (a.getAttribute("href") || "") : "";
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
    // 视频识别：有 <video> 标签 / .play-duration / .duration / .video-tag / 文字含"视频"
    const hasVideoTag = !!c.querySelector("video, .play-duration, .duration, .video-tag, .play-wrap, .video-icon");
    const txt = c.innerText || "";
    const hasVideoTxt = txt.indexOf("视频") > -1;
    const type = (hasVideoTag || hasVideoTxt) ? "视频" : "笔记";
    items.push({ id: mid, href: full, title, author, like, type, _videoTag: hasVideoTag });
  });
  const cont = document.querySelector(".ai-mode.user-page") || document.body;
  return JSON.stringify({
    count: items.length,
    contTop: cont.scrollTop,
    contSH: cont.scrollHeight,
    items
  });
})()
"""


def main():
    print(">>> 1. 导航到点赞页 ...")
    print(cmd("navigate", {"url": LIKED_URL, "newTab": True, "group_title": "小红书全量点赞统计"}))
    time.sleep(6)
    # 激活该 tab 为 Chrome 当前显示 tab（不抢窗口前台，但让 Chrome 标题变成小红书）
    cmd("cdp", {"method": "Page.bringToFront", "params": {}}, timeout=10)
    time.sleep(3)

    merged = {}
    last_count = -1
    no_new_rounds = 0
    max_rounds = 60

    for i in range(max_rounds):
        # 每轮先 force_foreground + OS 滚轮
        hwnd = find_chrome_hwnd()
        fg_ok = False
        if hwnd:
            fg_ok = force_foreground(hwnd)
        if fg_ok:
            os_wheel(delta=-120, n=6)
            time.sleep(1.8)
        else:
            # 退化方案：JS 滚动
            ev("document.querySelector('.ai-mode.user-page').scrollTop = 99999; 'ok'", timeout=8)
            time.sleep(1.5)

        # 提取
        raw = ev(EXTRACT_JS, timeout=30)
        try:
            data = json.loads(raw) if raw else {"items": []}
        except Exception:
            data = {"items": []}
        new_ids = []
        for it in data.get("items", []):
            if it["id"] not in merged:
                new_ids.append(it["id"])
            merged[it["id"]] = it

        cur = len(merged)
        v = sum(1 for x in merged.values() if x.get("type") == "视频")
        n = sum(1 for x in merged.values() if x.get("type") == "笔记")
        print(f"  轮 {i+1:2d}: 本页 {data.get('count',0)} / 新增 {len(new_ids)} / 累计 {cur} | 视频 {v} 笔记 {n} | 容器 top={data.get('contTop',0)}/{data.get('contSH',0)} | fg={fg_ok}")

        if cur == last_count:
            no_new_rounds += 1
            if no_new_rounds >= 8:
                print(f">>> 连续 8 轮无新增，停止。")
                break
        else:
            no_new_rounds = 0
        last_count = cur

    items = list(merged.values())
    v = sum(1 for it in items if it.get("type") == "视频")
    n = sum(1 for it in items if it.get("type") == "笔记")
    print("\n========== 最终统计 ==========")
    print(f"总点赞数（去重 note_id）: {len(items)}")
    print(f"  视频: {v}")
    print(f"  笔记: {n}")
    if items:
        print(f"  视频占比: {v/len(items)*100:.1f}%")
        print(f"  笔记占比: {n/len(items)*100:.1f}%")

    out = {"uid": UID, "total": len(items), "video": v, "note": n, "items": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n>>> 已保存: {OUT}")


if __name__ == "__main__":
    main()
