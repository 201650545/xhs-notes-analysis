# -*- coding: utf-8 -*-
"""批量深度分析过去的点赞笔记（100 条）—— 用点点 AI。
输入：_系统数据/_liked_snapshot.json
输出：b_answers/{note_id}.txt
跳过：已在 b_answers 存在的、做菜/影视解说类、拒绝词质量不过关的。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
HOME = "https://www.xiaohongshu.com/explore"
SNAP = r"D:\Work\小红书点赞分析\_系统数据\_liked_snapshot.json"
OUT_DIR = r"D:\Work\小红书点赞分析\b_answers"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 100
OFFSET = int(sys.argv[2]) if len(sys.argv) > 2 else 0

REFUSE = ["无法直接访问", "无法访问小红书", "暂时无法为您总结", "我目前无法",
          "请提供具体", "可以尝试以下方法", "我无法帮你"]
KW_EXCLUDE = ["炒牛肉", "炒肉", "做菜", "做饭", "食谱", "菜谱", "家常菜",
              "红烧", "清蒸", "烘焙", "怎么做好吃", "多少秒才好吃",
              "影视解说", "电影解说", "电视剧解说", "剧集解说", "剧情解说", "好剧解说",
              "影视剪辑", "影视混剪", "影视盘点", "一口气看完", "一剪到底"]

# 深度拆解提示词（短版 —— webbridge fill 对长文本有长度限制，长提示词会填充失败）
# 拿到 AI 回复后本地再按长模板组织成完整报告
PROMPT = ("请认真阅读这条小红书笔记，做深度拆解。输出：一、这是什么；二、素材与想法（素材从哪来、核心创意、巧妙之处）；"
          "三、实现方式（完整流程、技术原理、关键环节）；四、用到的AI与工具（逐个列出名称、用途、免费付费）；"
          "五、项目来源与链接（GitHub地址如有请原样给出，没有写未提供）；六、复现指南（前置条件、步骤、坑）；"
          "七、值得收藏的一句话。只依据笔记真实内容，没提到写笔记未提及。笔记链接：%s")


def cmd(action, args=None, timeout=90):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError("%s -> %s" % (action, json.dumps(r, ensure_ascii=False)[:200]))
    return r.get("data", {})


def ev(code):
    return cmd("evaluate", {"code": code})["value"]


def cdp(method, params=None):
    body = json.dumps({"action": "cdp", "args": {"method": method, "params": params or {}},
                       "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))


STATE_JS = r"""
(() => {
  const card = document.querySelector('.xhs-ai-selected-note-card');
  const ta = document.querySelector('#search-input-in-feeds');
  return JSON.stringify({hasCard:!!card, qlen: ta?ta.value.length:-1,
    title: card ? (card.querySelector('.xhs-ai-selected-note-title')?.innerText||'').trim():''});
})()
"""


def paste_link_as_card(href):
    subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $env:L"],
                   env={**os.environ, "L": href}, capture_output=True)
    time.sleep(0.5)
    ev("document.querySelector('#search-input-in-feeds').focus(); 'ok'")
    time.sleep(0.3)
    cdp("Page.bringToFront")
    time.sleep(0.6)
    for typ, p in [
        ("rawKeyDown", {"key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17, "nativeVirtualKeyCode": 17}),
        ("rawKeyDown", {"key": "v", "code": "KeyV", "windowsVirtualKeyCode": 86, "nativeVirtualKeyCode": 86, "modifiers": 2}),
        ("keyUp",      {"key": "v", "code": "KeyV", "windowsVirtualKeyCode": 86, "nativeVirtualKeyCode": 86, "modifiers": 2}),
        ("keyUp",      {"key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17, "nativeVirtualKeyCode": 17}),
    ]:
        cdp("Input.dispatchKeyEvent", {"type": typ, **p})
        time.sleep(0.12)
    for _ in range(12):
        time.sleep(1)
        try:
            if json.loads(ev(STATE_JS))["hasCard"]:
                return True
        except Exception:
            pass
    return False


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
  if (!ai.length) return JSON.stringify({state:'waiting', len:0, text:''});
  const x = ai[ai.length - 1];
  return JSON.stringify({
    state: x.className.indexOf('finished') > -1 ? 'done' : 'streaming',
    len: x.innerText.trim().length,
    text: x.innerText.trim()
  });
})()
"""

URL_JS = "location.href"


def quality(t):
    return len(t) > 400 and not any(k in t for k in REFUSE)


def excluded(title):
    return any(k in title for k in KW_EXCLUDE)


def wait_answer(timeout_s=240):
    last, stable = "", 0
    for i in range(timeout_s // 3):
        time.sleep(3)
        try:
            d = json.loads(ev(READ_JS))
        except Exception:
            continue
        if d.get("state") == "done":
            stable = stable + 1 if d.get("len") == len(last) and d.get("len") > 100 else 0
        last = d.get("text", "")
        if stable >= 2 and d.get("len", 0) > 100:
            return last
    return last


def run_one(href, prompt):
    cmd("navigate", {"url": HOME, "newTab": False})
    time.sleep(6.5)
    # 等待页面可交互（wendian-btn 可见且可点）
    for _ in range(20):
        try:
            if ev("!!document.querySelector('button.wendian-btn')") == "true":
                break
        except Exception:
            pass
        time.sleep(1)
    for _ in range(4):
        try:
            cmd("click", {"selector": "button.wendian-btn"})
        except Exception as e:
            print(f"      click 失败重试: {str(e)[:60]}", flush=True)
            time.sleep(3)
            continue
        time.sleep(3)
        try:
            if not paste_link_as_card(href):
                time.sleep(2)
                continue
        except Exception:
            time.sleep(2)
            continue
        time.sleep(1)
        try:
            cmd("fill", {"selector": "#search-input-in-feeds", "value": prompt})
            time.sleep(1.5)
        except Exception as e:
            print(f"      fill 失败重试: {str(e)[:60]}", flush=True)
            time.sleep(2)
            continue
        ev(ENTER_JS)
        time.sleep(6)
        if "ai_chat_tab" in ev(URL_JS):
            return wait_answer()
        time.sleep(2)
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    d = json.load(open(SNAP, encoding="utf-8"))
    items = d["items"]
    total = len(items)
    print(f">>> 快照共 {total} 条，本次跑 {LIMIT} 条（从 {OFFSET} 开始）", flush=True)

    ok = skip_exists = skip_excl = fail = 0
    fails = []

    for i in range(OFFSET, min(OFFSET + LIMIT, total)):
        it = items[i]
        nid = it["id"]
        title = it.get("title", "")
        href = f"https://www.xiaohongshu.com/explore/{nid}"

        # 跳过已存在
        out_path = os.path.join(OUT_DIR, f"{nid}.txt")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            skip_exists += 1
            print(f"[{i}] 跳过(已有) {title[:30]}", flush=True)
            continue
        # 跳过做菜/影视解说
        if excluded(title):
            skip_excl += 1
            print(f"[{i}] ⊘ 跳过(做菜/影视解说) {title[:30]}", flush=True)
            continue

        print(f"[{i}/{min(OFFSET+LIMIT,total)-1}] {title[:34]}", flush=True)
        prompt = PROMPT % href
        text = None
        for attempt in (1, 2):
            try:
                text = run_one(href, prompt)
            except Exception as e:
                print("     异常: %s" % str(e)[:80], flush=True)
                text = None
            if text and quality(text):
                break
            print(f"     重试(attempt {attempt}, 文本长度={len(text) if text else 0})", flush=True)
            time.sleep(3)

        if text and quality(text):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"【标题】{title}\n【作者】{it.get('author','')}\n【链接】{href}\n【类型】{it.get('type','')}\n\n【点点回复】\n{text}\n")
            ok += 1
            print(f"     ✅ {len(text)} 字 → {out_path}", flush=True)
        else:
            fail += 1
            fails.append((i, nid, title[:24]))
            print("     ❌ 失败", flush=True)
        time.sleep(2)

    print(f"\n>>> 完成：成功 {ok} | 跳过(已有) {skip_exists} | 跳过(做菜/影视) {skip_excl} | 失败 {fail}", flush=True)
    for f in fails:
        print("   失败:", f, flush=True)


if __name__ == "__main__":
    main()