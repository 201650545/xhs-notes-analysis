# -*- coding: utf-8 -*-
"""旧信息定时复核 · 任务C

机制（2026-09-24 用户需求）：
  笔记内容层永不过期（b_answers 是"笔记当时说了什么"的事实快照，不改不删）；
  时效层（免费额度/价格/版本/优惠）会过期或被新版替代，由本任务定时联网核查，
  判定 有效 / 已失效 / 已升级 / 无法核实，结果落 _review_state.json，
  由 scripts/obsidian/build_notes.ps1 渲染到 Obsidian 笔记（新结论置顶、旧分析折叠）。

核查通道：Kimi 网页版（kimi.com）+ Kimi WebBridge(127.0.0.1:10086)，session=kimi-review，
         提示词要求先联网搜索、只输出 JSON。每日上限默认 3 篇。

用法：
  python review_stale.py --init       只初始化/合并复核队列，不联网
  python review_stale.py --dry-run    打印今日到期队列，不联网
  python review_stale.py --selftest   打开 kimi.com 探测输入框/登录态，不发送
  python review_stale.py --probe      真实联网核查 1 篇（验证端到端）
  python review_stale.py              正式跑一轮（默认 3 篇），完成后重建 Obsidian 笔记
  python review_stale.py --limit 5
  python review_stale.py --no-rebuild 跑完不自动调 PowerShell 重建
"""
import os, re, json, sys, time, random, argparse, datetime, subprocess, urllib.request

BASE = r"<PROJECT_DIR>"
DATA = os.path.join(BASE, "_系统数据")  # 管线 JSON 系统数据（2026-09-28 起统一收纳，勿移出）
KB_FILE = os.path.join(DATA, "_knowledge_base.json")
STATE_FILE = os.path.join(DATA, "_review_state.json")
ANSWER_DIR = os.path.join(BASE, "b_answers")
REBUILD_PS1 = os.path.join(BASE, "scripts", "obsidian", "build_notes.ps1")

API = "http://127.0.0.1:10086/command"
SESSION = "kimi-review"
KIMI_HOME = "https://www.kimi.com/"

DAILY_LIMIT = 3
VALID = {"有效", "已失效", "已升级", "无法核实"}
STATUS_MAP = {"有效": "有效", "已失效": "已失效", "已升级": "已升级", "无法核实": "待人工核实"}

# 首次复核间隔（按入池类型）
FIRST_DAYS = {"sensitive": 0, "normal": 180}
# 判定后续期
RENEW_DAYS = {"有效": 45, "已升级": 60, "已失效": 180, "无法核实": 7}
MAX_FAILS = 3

# 时效敏感：标签命中即入高频复核池
TAG_HITS = ["免费", "白嫖", "额度", "token", "学生", "订阅", "定价", "价格",
            "gpt", "glm", "kimi", "cline", "deepseek", "qwen", "opencode",
            "devin", "zed", "zcode", "hermes", "api"]
# 撞款判定用的"实体"标签（同实体出现更新的笔记 → 提前复核）
ENTITY_TAGS = {"gpt6", "glm", "kimik3", "cline", "deepseek", "qwen", "opencode",
               "devin", "zed", "zcode", "hermes", "skill", "jev", "html"}

VERDICT_LABEL = {"有效": "✅ 仍然有效", "已失效": "❌ 已失效",
                 "已升级": "⬆️ 已有新版/升级", "无法核实": "❓ 无法核实"}


def log(m):
    print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), m), flush=True)


def load_json(p, default):
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def today():
    return datetime.date.today()


def d2s(d):
    return d.isoformat()


def is_sensitive(row):
    if row.get("category") == "A工具资源":
        return True
    tags = [str(t).lower() for t in (row.get("tags") or [])]
    return any(any(h in t for h in TAG_HITS) for t in tags)


def answer_mtime(row):
    try:
        return datetime.datetime.fromtimestamp(
            os.path.getmtime(os.path.join(ANSWER_DIR, row["file"]))).date()
    except Exception:
        return None


# ---------------- 队列初始化 / 合并 ----------------
def init_state():
    kb = load_json(KB_FILE, {"rows": []})
    st = load_json(STATE_FILE, {"version": 1, "notes": {}})
    notes = st.setdefault("notes", {})
    added = 0
    for r in kb["rows"]:
        nid = r["id"]
        if nid in notes:
            continue
        sens = is_sensitive(r)
        notes[nid] = {
            "title": r["title"], "cat": r["category"],
            "tags": r.get("tags") or [], "tier": "sensitive" if sens else "normal",
            "status": "待复核", "next_review": d2s(today() + datetime.timedelta(
                days=FIRST_DAYS["sensitive" if sens else "normal"])),
            "checked_at": None, "fails": 0, "reason": None, "history": [],
        }
        added += 1
    # 知识库中已删除的笔记不主动清（保留历史），仅更新时间戳
    st["updated_at"] = d2s(today())
    save_json(STATE_FILE, st)
    return kb, st, added


# ---------------- 到期选择 ----------------
def select_due(kb, st, limit):
    rows = {r["id"]: r for r in kb["rows"]}
    by_tag = {}
    for r in kb["rows"]:
        mt = answer_mtime(r)
        for t in (r.get("tags") or []):
            k = str(t).lower()
            if k in ENTITY_TAGS:
                by_tag.setdefault(k, []).append((r["id"], mt or datetime.date.min))

    due = []
    t0 = today()
    for nid, n in st["notes"].items():
        if nid not in rows:
            continue
        if n["status"] in ("已失效",):
            continue  # 失效后按超长周期自动回来，不提前
        reason = None
        try:
            nr = datetime.date.fromisoformat(n["next_review"])
            if nr <= t0:
                reason = "到期"
        except Exception:
            reason = "到期"
        # 撞款：同实体标签下存在分析时间更晚的笔记，且本篇复核早于它
        if reason is None:
            my_mt = answer_mtime(rows[nid]) or datetime.date.min
            for t in (rows[nid].get("tags") or []):
                k = str(t).lower()
                if k not in by_tag:
                    continue
                newer = [m for (i, m) in by_tag[k] if i != nid and m > my_mt]
                if newer and (not n["checked_at"] or
                              datetime.date.fromisoformat(n["checked_at"]) < max(newer)):
                    reason = "撞款:%s" % t
                    break
        if reason:
            n["reason"] = reason
            due.append((nid, reason))
    # 到期优先于撞款；sensitive 优先
    due.sort(key=lambda x: (0 if x[1] == "到期" else 1,
                            0 if st["notes"][x[0]]["tier"] == "sensitive" else 1))
    return due[:limit]


# ---------------- Kimi 网页驱动（kimi.com） ----------------
def cmd(action, args=None, timeout=120):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError(json.dumps(r, ensure_ascii=False)[:200])
    return r.get("data", {})


def ev(code):
    return cmd("evaluate", {"code": code})["value"]


def cdp(method, params=None, timeout=30):
    return cmd("cdp", {"method": method, "params": params or {}}, timeout=timeout)


PROBE_JS = r"""
(() => {
  const eds = [...document.querySelectorAll('textarea,[contenteditable="true"]')]
    .filter(e => e.offsetParent !== null)
    .map((e, i) => ({i, tag: e.tagName, ce: e.getAttribute('contenteditable'),
      ph: (e.placeholder || e.getAttribute('data-placeholder') || '').slice(0, 40),
      cls: (e.className && e.className.toString ? e.className.toString() : '').slice(0, 80),
      w: e.offsetWidth, h: e.offsetHeight}));
  return JSON.stringify({url: location.href, title: document.title.slice(0,60), editables: eds});
})()
"""


def probe():
    cmd("navigate", {"url": KIMI_HOME, "newTab": False})
    time.sleep(6)
    return json.loads(ev(PROBE_JS))


def _truth(v):
    return v is True or v == "true"


def wake_editor():
    """Kimi 首页输入框 contenteditable 默认 false，需鼠标活动后才懒激活。调用容错。"""
    for x in (320, 560, 820):
        try:
            cdp("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": 420})
        except Exception:
            pass
        time.sleep(0.3)


def _editor_ready():
    try:
        v = ev(r"""
(() => {
  const e = document.querySelector('.chat-input-editor');
  return !!(e && e.getAttribute('contenteditable') === 'true' && e.offsetParent !== null);
})()
""")
    except Exception:
        return False
    return _truth(v)


def wait_editor(timeout=25):
    """轮询等待 .chat-input-editor 激活（contenteditable=true 且可见），期间用鼠标唤醒。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _editor_ready():
            return True
        wake_editor()
        time.sleep(1.5)
    return False


def _editor_empty():
    v = ev("!(window.__rv_el && (window.__rv_el.value||window.__rv_el.innerText||'').trim().length)")
    return _truth(v)


def _click_send_button():
    """点击发送按钮兜底（有内容时按钮才可点）。"""
    return _truth(ev(r"""
(() => {
  const b = document.querySelector('.send-button-container:not(.disabled)');
  if (!b) return false;
  b.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
  b.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
  b.click();
  return true;
})()
"""))


def send_prompt(text):
    """唤醒 → 物理点击聚焦 → CDP 插入文本 → 回车（失败再点发送按钮）。
    返回 (是否成功, 失败阶段说明)。"""
    if not wait_editor():
        return False, "编辑器未激活"
    box = ev(r"""
(() => {
  const e = document.querySelector('.chat-input-editor');
  if (!e || e.getAttribute('contenteditable') !== 'true') return null;
  const r = e.getBoundingClientRect();
  window.__rv_el = e;
  e.focus();
  return JSON.stringify({x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)});
})()
""")
    if not box:
        return False, "聚焦前编辑器失活"
    try:
        b = json.loads(box)
        cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": b["x"], "y": b["y"],
                                        "button": "left", "clickCount": 1})
        cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": b["x"], "y": b["y"],
                                        "button": "left", "clickCount": 1})
    except Exception:
        pass
    time.sleep(0.5)
    try:
        cdp("Input.insertText", {"text": text})
    except Exception as e:
        return False, "insertText异常:%s" % str(e)[:80]
    time.sleep(1.0)
    filled = ev("!!(window.__rv_el && (window.__rv_el.value||window.__rv_el.innerText||'').trim().length)")
    if not _truth(filled):
        return False, "文本未进入输入框"
    for typ in ("rawKeyDown", "keyUp"):
        try:
            cdp("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                           "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        except Exception:
            pass
        time.sleep(0.2)
    time.sleep(4)
    if _editor_empty():
        return True, ""
    if _click_send_button():
        time.sleep(4)
        if _editor_empty():
            return True, ""
    ev(r"""
(() => {
  const el = window.__rv_el; if (!el) return 0;
  const o = {key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true};
  ['keydown','keypress','keyup'].forEach(t => el.dispatchEvent(new KeyboardEvent(t, o)));
  return 1;
})()
""")
    time.sleep(4)
    return _editor_empty(), "回车与发送按钮均未清空输入框"


JSON_RE = re.compile(r'\{[^{}]*"verdict"[^{}]*\}', re.S)


def extract_verdict(page_text):
    """从整页文本里抓含 verdict 的 JSON（不依赖消息容器选择器）。"""
    for m in JSON_RE.finditer(page_text):
        raw = m.group(0)
        try:
            d = json.loads(raw)
        except Exception:
            continue
        v = str(d.get("verdict", "")).strip()
        if v in VALID:
            return d
    return None


def wait_verdict(timeout_s=200):
    last_sig = None
    stable = 0
    for _ in range(timeout_s // 4):
        time.sleep(4)
        try:
            txt = ev("document.body.innerText") or ""
        except Exception:
            continue
        d = extract_verdict(txt)
        if d:
            sig = d.get("verdict") + "|" + str(len(str(d.get("current_facts", ""))))
            if sig == last_sig:
                stable += 1
            else:
                stable = 0
                last_sig = sig
            if stable >= 1:
                return d
    return None


# ---------------- 提示词与判定 ----------------
def build_prompt(row, analysis_body):
    return """请联网搜索核实一条旧笔记里的时效信息今天（%s）是否仍成立。先搜索官方公告/定价页/活动页，再下结论。

【笔记标题】%s
【当时分析全文】
%s

只输出一个 JSON 对象，不要 markdown 围栏、不要任何解释：
{"verdict":"有效|已失效|已升级|无法核实","current_facts":"现在的实际情况，2-4句，含关键数字/版本号/价格","changes":"相对旧信息具体变了什么；没变写无","new_summary":"仅当已升级时：更新后的一句话总结，否则空字符串","sources":"依据的1-3个来源（名称+网址），用；分隔","confidence":0}

判定标准：
- 有效：旧信息里的免费额度/优惠/价格/版本今天仍可获得且准确
- 已失效：活动结束、开始收费、入口关闭、产品停更
- 已升级：出现新一代版本或更好的官方替代，旧内容明显过时（如 K3 出了 K4）
- 无法核实：搜不到可靠证据（不要猜）""" % (
        d2s(today()), row["title"], analysis_body[:6000])


def verify_one(row):
    fp = os.path.join(ANSWER_DIR, row["file"])
    body = open(fp, encoding="utf-8").read()
    prompt = build_prompt(row, body)
    cmd("navigate", {"url": KIMI_HOME, "newTab": False})
    time.sleep(5)
    ok, why = send_prompt(prompt)
    if not ok:
        return None, "发送失败（%s）" % why
    d = wait_verdict()
    if not d:
        return None, "超时未取得合法 JSON"
    return d, None


def apply_verdict(n, d):
    v = str(d["verdict"]).strip()
    n["checked_at"] = d2s(today())
    n["history"].insert(0, {
        "date": d2s(today()), "verdict": v,
        "facts": str(d.get("current_facts", "")).strip(),
        "changes": str(d.get("changes", "")).strip(),
        "new_summary": str(d.get("new_summary", "")).strip(),
        "sources": str(d.get("sources", "")).strip(),
    })
    n["history"] = n["history"][:10]
    n["status"] = STATUS_MAP[v]
    if v == "无法核实":
        n["fails"] = int(n.get("fails", 0)) + 1
        gap = 30 if n["fails"] >= MAX_FAILS else RENEW_DAYS[v]
    else:
        n["fails"] = 0
        gap = RENEW_DAYS[v]
    n["next_review"] = d2s(today() + datetime.timedelta(days=gap))


# ---------------- 主流程 ----------------
def rebuild_notes():
    if not os.path.exists(REBUILD_PS1):
        return False
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", REBUILD_PS1], timeout=180,
                       capture_output=True)
        return True
    except Exception as e:
        log("重建 Obsidian 笔记失败：%s" % str(e)[:120])
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--limit", type=int, default=DAILY_LIMIT)
    ap.add_argument("--no-rebuild", action="store_true")
    ap.add_argument("--no-lark", action="store_true", help="不向飞书镜像推送本轮复核结果")
    args = ap.parse_args()

    kb, st, added = init_state()
    log("队列就绪：共 %d 篇（新入队 %d）" % (len(st["notes"]), added))

    if args.init:
        return

    if args.selftest:
        print(json.dumps(probe(), ensure_ascii=False, indent=1))
        return

    due = select_due(kb, st, 999 if (args.dry_run or args.probe) else args.limit)
    if args.dry_run:
        log("今日到期 %d 篇：" % len(due))
        for nid, why in due:
            n = st["notes"][nid]
            print("  [%s] %s | tier=%s next=%s reason=%s | %s"
                  % (n["status"], nid, n["tier"], n["next_review"], why, n["title"][:34]))
        return
    if not due:
        log("没有到期需要复核的笔记")
        return

    if args.probe:
        due = due[:1]
        log("PROBE 模式：真实核查 1 篇")

    done = 0
    done_ids = []
    for nid, why in due:
        n = st["notes"][nid]
        row = next(r for r in kb["rows"] if r["id"] == nid)
        log("复核（%s）%s" % (why, n["title"][:36]))
        try:
            d, err = verify_one(row)
        except Exception as e:
            d, err = None, "异常：%s" % str(e)[:150]
        if not d:
            n["fails"] = int(n.get("fails", 0)) + 1
            n["next_review"] = d2s(today() + datetime.timedelta(
                days=30 if n["fails"] >= MAX_FAILS else 7))
            n["status"] = "待人工核实" if n["fails"] >= MAX_FAILS else "待复核"
            log("  ✗ %s（fails=%d）" % (err, n["fails"]))
        else:
            apply_verdict(n, d)
            done += 1
            done_ids.append(nid)
            log("  → %s | %s" % (VERDICT_LABEL.get(d["verdict"], d["verdict"]),
                                 str(d.get("current_facts", ""))[:80]))
        save_json(STATE_FILE, st)
        time.sleep(random.uniform(3, 6))

    log("本轮完成：成功判定 %d / %d" % (done, len(due)))
    if done and not args.no_rebuild:
        log("重建 Obsidian 笔记 ...")
        rebuild_notes()
    if done_ids and not args.no_lark:
        push_lark(done_ids)


def push_lark(nids):
    """复核结果单向上行飞书镜像；失败不影响主管线。"""
    try:
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "route_sync.py"),
                "--review-push", "--ids", ",".join(nids)],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                capture_output=True, text=True, encoding="utf-8", timeout=300)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        log("飞书镜像：" + (out[-1][:120] if out else "无输出"))
    except Exception as e:
        log("飞书镜像推送失败（不影响本地）：%s" % str(e)[:120])


if __name__ == "__main__":
    main()
