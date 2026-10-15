# -*- coding: utf-8 -*-
"""小红书点赞管理 · 每日定时任务（纯页面内原生 API 版）

三个任务：
  A) unlike_old   最近 100 篇之外的旧点赞，每天取消 50~100 个（随机），从最旧开始
   B) process_new  每天处理新增点赞：跑 v3 深度分析（问点点），处理完即取消点赞；
                   做菜类、影视解说类不分析直接取消；分析失败保留点赞次日重试（最多 MAX_ANALYZE_ATTEMPTS 次，
                   超过则放弃分析直接取消，不留“分析不了又取消不掉”的死链）；
                   已有分析全文的直接补取消，不重复烧点点
  C) review_stale 旧信息时效复核：Kimi 联网核查福利/价格/版本是否有效、是否已升级，
                  每日≤3篇，结果写 _review_state.json 并重建 Obsidian 笔记（见 review_stale.py）

实现方式（关键）：
  - 不做 OS 点击/滚轮，不抢窗口焦点，锁屏/后台均可跑
  - 复用站点自己的 webpack 模块 25717：
      RZ  getApiSnsWebV1NoteLikePage  GET  /api/sns/web/v1/note/like/page
      ny  postApiSnsWebV1NoteDislike  POST /api/sns/web/v1/note/dislike  body={noteOid}
    签名(X-s/X-t/X-S-Common)由站点拦截器自动完成
  - 点赞 tab 必须在页面上点出来（冷加载 ?tab=liked 会被重定向到 note）

用法：
  python xhs_like_manager.py                 # 跑一轮 A+B
  python xhs_like_manager.py --enumerate-only# 只拉取全量列表核对数量
  python xhs_like_manager.py --only A        # 只跑 A
  python xhs_like_manager.py --only B        # 只跑 B
  python xhs_like_manager.py --quota 5       # 指定 A 今日取消数（测试用）
  python xhs_like_manager.py --daemon        # 常驻，每 24h 一轮
  python xhs_like_manager.py --session xhs2  # 复用指定浏览器会话

依赖：Kimi WebBridge 守护进程 127.0.0.1:10086 + Chrome 已登录小红书
"""
import json, time, random, urllib.request, os, sys, argparse, datetime, traceback, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402

API = "http://127.0.0.1:10086/command"
DEFAULT_SESSION = "xhs-mgr"
UID = get_cred("XHS_USER_ID", "<XHS_USER_ID>")
PROFILE_URL = "https://www.xiaohongshu.com/user/profile/%s" % UID

KEEP_RECENT = 100                 # 最近 N 篇保留
DAILY_UNLIKE_MIN, DAILY_UNLIKE_MAX = 50, 100
B_DAILY_MAX = 20                  # 任务B 每日分析上限（防风控）
MAX_ANALYZE_ATTEMPTS = 3          # 单篇分析最多重试轮数，超过则放弃分析直接取消点赞
PAGE_DELAY = (0.9, 1.6)           # 翻页随机间隔
UNLIKE_DELAY = (3.5, 7.0)         # 取消点赞随机间隔
PAGES_PER_CHUNK = 8               # 每次 evaluate 连续拉取页数
MAX_ITEMS = 4000

BASE_DIR = r"<PROJECT_DIR>"
DATA_DIR = os.path.join(BASE_DIR, "_系统数据")  # 管线 JSON 系统数据（2026-09-28 起统一收纳，勿移出）
WB_EXE = os.path.expanduser(r"~\.kimi-webbridge\bin\kimi-webbridge.exe")
PROGRESS_FILE = os.path.join(DATA_DIR, "_unlike_progress.json")
NEW_TASKS_FILE = os.path.join(DATA_DIR, "_new_tasks.json")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "_liked_snapshot.json")
ANSWER_DIR = os.path.join(BASE_DIR, "b_answers")
LOG_DIR = os.path.join(BASE_DIR, "logs")


def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "mgr_%s.log" % datetime.date.today().isoformat()),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def has_analysis(nid):
    """安全落盘前置检查：取消点赞前确认该笔记已存在分析全文。
    GPT-6 审查 20261015 P0-3：任务 A/B 取消点赞前必须已落盘，否则保留点赞。"""
    return os.path.isfile(os.path.join(ANSWER_DIR, nid + ".txt"))


# ---------------- WebBridge ----------------
class XHS:
    def __init__(self, session):
        self.session = session

    def cmd(self, action, args=None, timeout=90):
        payload = {"action": action, "args": args or {}, "session": self.session}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ev(self, code, timeout=90):
        r = self.cmd("evaluate", {"code": code}, timeout=timeout)
        if r.get("ok"):
            return r.get("data", {}).get("value", "")
        return None

    def alive(self):
        v = self.ev("location.href", timeout=10)
        return bool(v) and "xiaohongshu.com" in v

    # ---------- 页面引导 ----------
    def navigate(self, url, new_tab):
        return self.cmd("navigate", {"url": url, "newTab": new_tab,
                                     "group_title": "小红书点赞管理"}, timeout=40)

    def wait_spa(self, max_s=22):
        end = time.time() + max_s
        while time.time() < end:
            v = self.ev("String(!!window.webpackChunkxhs_pc_web && document.querySelectorAll('.reds-tab-item').length > 0)",
                        timeout=10)
            if v == "true":
                return True
            time.sleep(1.5)
        return False

    CLICK_LIKED_JS = r"""
    (() => {
      let t = null;
      document.querySelectorAll('.reds-tab-item').forEach(el => {
        if ((el.innerText||'').trim() === '点赞' && el.offsetParent) t = el;
      });
      if (!t) return 'no_tab';
      t.click();
      return 'ok';
    })()
    """

    def click_liked_tab(self):
        if self.ev(self.CLICK_LIKED_JS, timeout=10) != "ok":
            return False
        end = time.time() + 10
        while time.time() < end:
            u = self.ev("location.href", timeout=8) or ""
            if "tab=liked" in u:
                time.sleep(2.5)   # 等列表接口预热
                return True
            time.sleep(1)
        return False

    INIT_JS = r"""
    (() => {
      try {
        if (window.__mgrApi) { try { void window.__mgrApi.RZ; return 'ready'; } catch(e){} }
        if (!window.__wreq) {
          window.webpackChunkxhs_pc_web.push([["__mgr_" + Date.now()], {}, function(r){ window.__wreq = r; }]);
        }
        const mm = window.__wreq(25717);
        window.__mgrApi = {RZ: mm.RZ, ny: mm.ny};
        return (typeof mm.RZ === 'function' && typeof mm.ny === 'function') ? 'ready' : 'missing_fn';
      } catch(e) { return 'err:' + String(e).slice(0,120); }
    })()
    """

    def init_api(self):
        v = self.ev(self.INIT_JS, timeout=20)
        return v == "ready"

    def bootstrap(self, allow_new_tab=True):
        """确保：标签页在点赞 tab，API 可用。返回 True/False。"""
        if not self.alive():
            if not allow_new_tab:
                log("会话不存在且不允许新建标签")
                return False
            log("会话不可用，新建标签页 ...")
            self.navigate(PROFILE_URL, True)
            time.sleep(7)
        else:
            u = self.ev("location.href", timeout=8) or ""
            if "/user/profile/%s" % UID not in u:
                log("导航到个人主页 ...")
                self.navigate(PROFILE_URL, False)
                time.sleep(6)
        if not self.wait_spa():
            log("SPA 未就绪"); return False
        u = self.ev("location.href", timeout=8) or ""
        if "tab=liked" not in u:
            log("点击「点赞」tab ...")
            if not self.click_liked_tab():
                log("无法进入点赞 tab"); return False
        if not self.init_api():
            log("API 模块注入失败"); return False
        # 预热：实际拉一页，冷启动安全模块未就绪会 -9109，重试
        for i in range(4):
            r = self.fetch_chunk("", 1)
            if r.get("ok"):
                return True
            log("API 预热失败(%d)：%s，重试 ..." % (i + 1, r.get("lastErr") or r.get("err")))
            time.sleep(3)
        return False

    # ---------- 列表翻页 ----------
    CHUNK_JS = r"""
    (async () => {
      try {
        if (!window.__mgrApi) {
          if (!window.__wreq) window.webpackChunkxhs_pc_web.push([["__mgr_"+Date.now()],{},function(r){window.__wreq=r;}]);
          const mm0 = window.__wreq(25717);
          window.__mgrApi = {RZ: mm0.RZ, ny: mm0.ny};
        }
        const api = window.__mgrApi;
        let cursor = "__CURSOR__";
        const notes = [];
        let hasMore = true, lastErr = null, pagesDone = 0;
        for (let p = 0; p < __PAGES__; p++) {
          let r = null, ok = false;
          for (let tr = 0; tr < 3 && !ok; tr++) {
            try {
              r = await api.RZ({params: {num: 30, cursor: cursor, user_id: "__UID__",
                image_formats: "jpg,webp,avif", xsec_token: "", xsec_source: ""}});
              ok = true;
            } catch (e) {
              lastErr = String(e && (e.message || e.msg || e));
              await new Promise(z => setTimeout(z, 2500));
            }
          }
          if (!ok) break;
          (r.notes || []).forEach(n => notes.push({
            id: n.noteId, type: n.type, title: n.displayTitle || "",
            token: n.xsecToken || "",
            author: (n.user && n.user.nickname) || "",
            liked: !!(n.interactInfo && n.interactInfo.liked)
          }));
          pagesDone++;
          cursor = r.cursor || "";
          hasMore = !!r.hasMore;
          if (!hasMore) break;
          if (p < __PAGES__ - 1) await new Promise(z => setTimeout(z, __DELAY__));
        }
        return JSON.stringify({ok: true, notes, cursor, hasMore, pagesDone, lastErr});
      } catch (e) {
        return JSON.stringify({ok: false, err: String(e && (e.message || e.msg || e))});
      }
    })()
    """

    def fetch_chunk(self, cursor, pages=PAGES_PER_CHUNK, delay_ms=None):
        js = (self.CHUNK_JS
              .replace("__CURSOR__", cursor.replace('"', ''))
              .replace("__PAGES__", str(pages))
              .replace("__UID__", UID)
              .replace("__DELAY__", str(int((delay_ms or random.randint(*[int(x*1000) for x in PAGE_DELAY]))))))
        raw = self.ev(js, timeout=150)
        try:
            return json.loads(raw) if raw else {"ok": False, "err": "empty_response"}
        except Exception:
            return {"ok": False, "err": "bad_json", "raw": (raw or "")[:200]}

    def enumerate_likes(self, max_items=MAX_ITEMS, progress_cb=None):
        """全量拉取点赞列表（新→旧），返回 items。断点快照每块落盘。"""
        items, seen, cursor, has_more = [], set(), "", True
        guard = 0
        while has_more and len(items) < max_items and guard < 400:
            guard += 1
            r = self.fetch_chunk(cursor)
            if not r.get("ok"):
                # 整块连续失败：重新引导一次再试
                log("翻页块失败：%s，重新引导 ..." % (r.get("lastErr") or r.get("err")))
                if not self.bootstrap(allow_new_tab=False):
                    raise RuntimeError("enumerate aborted: %s" % (r.get("lastErr") or r.get("err")))
                continue
            added = 0
            for n in r.get("notes", []):
                if n["id"] and n["id"] not in seen:
                    seen.add(n["id"]); items.append(n); added += 1
            cursor = r.get("cursor", "")
            has_more = r.get("hasMore", False)
            save_json(SNAPSHOT_FILE, {"ts": datetime.datetime.now().isoformat(),
                                      "count": len(items), "cursor": cursor,
                                      "has_more": has_more, "items": items})
            if progress_cb:
                progress_cb(len(items), has_more)
            time.sleep(random.uniform(0.4, 1.0))
        return items

    # ---------- 取消点赞 ----------
    UNLIKE_JS = r"""
    (async () => {
      try {
        if (!window.__mgrApi) {
          if (!window.__wreq) window.webpackChunkxhs_pc_web.push([["__mgr_"+Date.now()],{},function(r){window.__wreq=r;}]);
          const mm0 = window.__wreq(25717);
          window.__mgrApi = {RZ: mm0.RZ, ny: mm0.ny};
        }
        const r = await window.__mgrApi.ny({noteOid: "__ID__"});
        return JSON.stringify({ok: true, resp: r});
      } catch (e) {
        return JSON.stringify({ok: false, msg: String(e && (e.message || e.msg || e)),
                              raw: JSON.stringify(e).slice(0, 300)});
      }
    })()
    """

    def unlike(self, note_id):
        raw = self.ev(self.UNLIKE_JS.replace("__ID__", note_id), timeout=40)
        try:
            r = json.loads(raw) if raw else {}
        except Exception:
            r = {}
        return r


# ---------------- 存储 ----------------
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ---------------- 任务 A ----------------
def task_unlike_old(xhs, quota_override=None):
    log("===== 任务A：取消旧点赞（保留最近 %d 篇）=====" % KEEP_RECENT)
    prog = load_json(PROGRESS_FILE, {"cancelled": []})
    cancelled = set(prog.get("cancelled", []))

    # 引导失败重试 2 次再跳过（SPA 未就绪多为瞬时，一次失败就跳过会整轮不取消）
    booted = False
    for i in range(3):
        if xhs.bootstrap():
            booted = True
            break
        if i < 2:
            log("引导失败，25 秒后重试（%d/3）..." % (i + 1))
            time.sleep(25)
    if not booted:
        log("任务A：环境引导失败，跳过"); return

    log("全量拉取点赞列表 ...")
    items = xhs.enumerate_likes(progress_cb=lambda n, hm: log("  已拉取 %d 条 ..." % n) if n % 200 < 80 else None)
    total = len(items)
    log("点赞总数：%d" % total)
    save_json(SNAPSHOT_FILE, {"ts": datetime.datetime.now().isoformat(), "count": total, "items": items})

    quota = quota_override or random.randint(DAILY_UNLIKE_MIN, DAILY_UNLIKE_MAX)
    # 最近 KEEP_RECENT 保留；从最旧开始取消
    targets = [it for it in reversed(items[KEEP_RECENT:]) if it["id"] not in cancelled]
    log("待取消存量：%d | 今日配额：%d | 已取消：%d" % (len(targets), quota, len(cancelled)))

    done = fail_streak = skipped_no_analysis = 0
    for it in targets:
        if done >= quota:
            break
        nid = it["id"]
        # P0-3（2026-10-15）：安全落盘前置检查——没有分析全文的笔记不取消，保留点赞
        if not has_analysis(nid):
            skipped_no_analysis += 1
            continue
        r = xhs.unlike(nid)
        if r.get("ok"):
            cancelled.add(nid)
            prog["cancelled"] = sorted(cancelled)
            prog["last_run"] = datetime.datetime.now().isoformat()
            save_json(PROGRESS_FILE, prog)
            done += 1; fail_streak = 0
            log("  A [%d/%d] 取消 ✓ %s %s（likeCount=%s）" % (
                done, quota, nid, it.get("title", "")[:24],
                (r.get("resp") or {}).get("likeCount")))
            time.sleep(random.uniform(*UNLIKE_DELAY))
        else:
            fail_streak += 1
            log("  A 取消失败 %s：%s" % (nid, r.get("msg") or r.get("raw")))
            if fail_streak >= 5:
                log("连续失败 5 次，终止本轮（可能触发风控）"); break
            time.sleep(5)
    log("任务A完成：今日取消 %d，累计取消 %d，剩余点赞约 %d（其中无分析保留 %d）" % (
        done, len(cancelled), total - len(cancelled), skipped_no_analysis))


# ---------------- 任务 B ----------------
def note_href(uid, it):
    return ("https://www.xiaohongshu.com/user/profile/%s/%s?xsec_token=%s&xsec_source=pc_user"
            % (uid, it["id"], it.get("token", "")))


def route_and_sync(nid, title, href, ans, rec, it=None):
    """分析完成后加一步「行动路由」：问点点一次短提问 → 解析 → 落盘 → 写入飞书（进 01 待拍板）。
    任何环节失败都不影响分析结果与取消点赞，只记录状态。"""
    import batch_final, route_sync
    route = None
    try:
        rt = batch_final.run_one(href, batch_final.ROUTE_PROMPT)
        route = route_sync.parse_routing(rt or "")
    except Exception as e:
        log("    路由提问异常：%s" % str(e)[:120])
    if not route:
        log("    路由解析失败，按仅了解入库（可人工补）")
    try:
        route_sync.save_route(nid, route)
    except Exception as e:
        log("    路由落盘失败：%s" % str(e)[:120])
    try:
        rid = route_sync.write_lark(nid, title, href, ans, route, it=it)
        rec["lark"] = rid
        rec["route"] = (route or {}).get("路由") or "未解析"
        log("    入库 ✓ %s（路由=%s）" % (rid, rec["route"]))
    except Exception as e:
        rec["lark_error"] = str(e)[:200]
        log("    入库失败：%s（存档已就绪，可跑 sync_lark_99 --incremental 补写）" % str(e)[:150])


def task_process_new(xhs):
    log("===== 任务B：处理新增点赞（v3 分析后取消）=====")
    state = load_json(NEW_TASKS_FILE, {"baseline": [], "processed": [], "records": []})
    baseline = set(state.get("baseline", []))
    processed = set(state.get("processed", []))
    fail_counts = state.get("fail_counts", {})
    pending_cancel = set(state.get("pending_cancel", []))

    if not xhs.bootstrap():
        log("任务B：环境引导失败，跳过"); return
    items = xhs.enumerate_likes(max_items=300)
    top = items[:KEEP_RECENT]

    # 首次运行：把当前最近 100 篇设为基线，不回溯分析
    if not baseline:
        baseline = {it["id"] for it in top}
        state["baseline"] = sorted(baseline)
        state["seeded_at"] = datetime.datetime.now().isoformat()
        save_json(NEW_TASKS_FILE, state)
        log("首次运行：已播种基线 %d 篇（不回溯分析）" % len(baseline))

    # 候选池放到整个枚举范围（300）而不只是最近 100：往轮被挂起的欠账（如取消阶段
    # 引导失败、跨轮重试）跌出 top100 后也要能捞回来，否则永远够不着。
    def _is_cand(it):
        return it["id"] not in baseline and it["id"] not in processed

    cand_new = [it for it in items if _is_cand(it)]
    # 欠账优先：上轮分析完/待取消没销掉的先还，再装新候选
    owes = [it for it in cand_new if it["id"] in pending_cancel]
    cand_new = [it for it in cand_new if it["id"] not in pending_cancel]
    candidates = (owes + cand_new)[:B_DAILY_MAX]
    log("今日待处理：%d 篇（其中补取消/重试 %d）" % (len(candidates), len(owes[:B_DAILY_MAX])))
    if not candidates:
        state["pending_cancel"] = sorted(pending_cancel)
        save_json(NEW_TASKS_FILE, state)
        return

    import batch_final
    batch_final.SESSION = xhs.session
    os.makedirs(ANSWER_DIR, exist_ok=True)

    pending_unlike = []
    for i, it in enumerate(candidates):
        nid = it["id"]; title = it.get("title", "")
        rec = {"id": nid, "title": title, "type": it.get("type"), "ts": datetime.datetime.now().isoformat()}
        fp = os.path.join(ANSWER_DIR, "%s.txt" % nid)
        if batch_final.excluded(nid, title):
            rec["status"] = "excluded"; rec["detail"] = "做菜/影视解说类，不分析直接取消"
            pending_unlike.append(nid); processed.add(nid)
            log("  B [%d] 跳过分析(做菜/影视解说) %s" % (i + 1, title[:24]))
        elif os.path.exists(fp):
            # 已有分析全文（多为往轮取消阶段失败被挂起的）：不重复烧点点，直接补取消
            rec["status"] = "already_analyzed"; rec["file"] = fp
            pending_unlike.append(nid); processed.add(nid)
            log("  B [%d] 已有分析全文，直接补取消 %s" % (i + 1, title[:24]))
        else:
            prompt = batch_final.PROMPTS[batch_final.classify(title)]
            href = note_href(UID, it)
            log("  B [%d] 分析中：%s" % (i + 1, title[:30]))
            try:
                ans = batch_final.run_one(href, prompt)
            except Exception as e:
                ans = None
                log("    run_one 异常：%s" % str(e)[:150])
            if ans and batch_final.quality(ans):
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("# %s v3\n# %s\n# %s\n\n%s" % (batch_final.VERSION, title, href, ans))
                rec["status"] = "analyzed"; rec["file"] = fp
                pending_unlike.append(nid); processed.add(nid)
                fail_counts.pop(nid, None)
                log("    分析完成 ✓ (%d 字)" % len(ans))
                route_and_sync(nid, title, href, ans, rec, it)
            else:
                tries = fail_counts.get(nid, 0) + 1
                if tries >= MAX_ANALYZE_ATTEMPTS:
                    # P0-3（2026-10-15，GPT-6 建议）：分析失败 N 次后不再直接取消点赞。
                    # 改为保留点赞 + 标记 giveup_keep，由人工决定是否最终取消。
                    # 避免"未分析就取消"导致高价值笔记永久丢失。
                    rec["status"] = "giveup_keep"
                    rec["detail"] = "分析 %d 次均失败，保留点赞等待人工处理" % tries
                    processed.add(nid)
                    fail_counts.pop(nid, None)
                    log("    分析失败（第 %d 次），保留点赞待人工处理（不取消）" % tries)
                else:
                    fail_counts[nid] = tries
                    rec["status"] = "failed"
                    rec["detail"] = "分析失败，保留点赞次日重试（%d/%d）" % (tries, MAX_ANALYZE_ATTEMPTS)
                    log("    分析失败，保留点赞（%d/%d，次日重试）" % (tries, MAX_ANALYZE_ATTEMPTS))
        state["fail_counts"] = fail_counts
        state["pending_cancel"] = sorted(set(pending_cancel) | set(pending_unlike))
        state["records"].append(rec)
        save_json(NEW_TASKS_FILE, state)
        time.sleep(random.uniform(2, 4))

    # 分析阶段会把标签页切到问点点，取消前重新引导回点赞 tab
    if pending_unlike:
        log("分析结束，回到点赞 tab 执行取消（共 %d 篇）..." % len(pending_unlike))
        # 欠账先落盘：进程中途被杀也不丢（下轮启动会优先还这部分）
        state["pending_cancel"] = sorted(set(pending_cancel) | set(pending_unlike))
        save_json(NEW_TASKS_FILE, state)
        if not xhs.bootstrap():
            # 关键修复（2026-10-09）：引导失败时不能把这些笔记留在 processed 里——
            # 一旦标记过就永远不再是候选，赞再也取消不掉（10-01/10-02 两天曾因此坑了 39 篇）。
            # 全部摘掉 processed，下轮重新走流程。
            log("无法回到点赞 tab，%d 篇改回待处理（下轮重试），不标记为已完成" % len(pending_unlike))
            for nid in pending_unlike:
                processed.discard(nid)
            state["processed"] = sorted(processed)
            state["pending_cancel"] = sorted(set(pending_cancel) | set(pending_unlike))
            save_json(NEW_TASKS_FILE, state)
            return
        for nid in pending_unlike:
            # P0-3（2026-10-15）：取消前再次确认安全落盘，避免意外取消未分析笔记
            if not has_analysis(nid):
                log("  B 跳过（无分析全文）：%s（保留点赞）" % nid)
                processed.discard(nid)
                continue
            r = xhs.unlike(nid)
            if r.get("ok"):
                pending_cancel.discard(nid)
                log("  B 取消 ✓ %s（likeCount=%s）" % (nid, (r.get("resp") or {}).get("likeCount")))
            else:
                log("  B 取消失败 %s：%s（下轮重试）" % (nid, r.get("msg") or r.get("raw")))
                processed.discard(nid)   # 未取消成功，下轮继续
            state["processed"] = sorted(processed)
            state["pending_cancel"] = sorted(pending_cancel)
            save_json(NEW_TASKS_FILE, state)
            time.sleep(random.uniform(*UNLIKE_DELAY))
    log("任务B完成：分析/取消 %d 篇" % len(pending_unlike))


# ---------------- 回溯补做（9月以来存量） ----------------
def task_backfill(xhs, n, limit=0):
    log("===== 回溯补做：最近 %d 篇跑 v3 分析后取消（新分析上限 %s）=====" % (n, limit or "无"))
    state = load_json(NEW_TASKS_FILE, {"baseline": [], "processed": [], "records": [],
                                       "backfill_done": [], "backfill_failed": []})
    bf_done = set(state.get("backfill_done", []))
    baseline = set(state.get("baseline", []))
    processed = set(state.get("processed", []))

    if not xhs.bootstrap():
        log("回溯：环境引导失败"); return
    log("拉取最近 %d 篇 ..." % n)
    items = xhs.enumerate_likes(max_items=n + 20)[:n]
    log("实际取得 %d 篇" % len(items))

    import batch_final
    batch_final.SESSION = xhs.session
    os.makedirs(ANSWER_DIR, exist_ok=True)

    pending_unlike, failed_now = [], []
    analyzed_n = skipped_n = fail_n = 0
    for i, it in enumerate(items):
        nid, title = it["id"], it.get("title", "")
        if nid in bf_done:
            skipped_n += 1
            continue
        fp = os.path.join(ANSWER_DIR, "%s.txt" % nid)
        rec = {"id": nid, "title": title, "type": it.get("type"),
               "ts": datetime.datetime.now().isoformat(), "mode": "backfill"}
        if os.path.exists(fp) or batch_final.excluded(nid, title):
            if os.path.exists(fp):
                rec["status"] = "already_analyzed"; skipped_n += 1
            else:
                rec["status"] = "excluded"; rec["detail"] = "做菜/影视解说类不分析"
            pending_unlike.append((nid, it, fp if os.path.exists(fp) else None))
            state["records"].append(rec)
            save_json(NEW_TASKS_FILE, state)
            continue
        prompt = batch_final.PROMPTS[batch_final.classify(title)]
        href = note_href(UID, it)
        log("  回溯 [%d/%d] 分析：%s" % (i + 1, len(items), title[:32]))
        ans = None
        try:
            ans = batch_final.run_one(href, prompt)
        except Exception as e:
            log("    run_one 异常：%s" % str(e)[:150])
        if ans and batch_final.quality(ans):
            with open(fp, "w", encoding="utf-8") as f:
                f.write("# %s v3（回溯）\n# %s\n# %s\n\n%s" % (batch_final.VERSION, title, href, ans))
            rec["status"] = "analyzed"; rec["file"] = fp
            pending_unlike.append((nid, it, fp))
            analyzed_n += 1
            log("    ✓ 完成（%d 字），待统一取消" % len(ans))
            route_and_sync(nid, title, href, ans, rec, it)
        else:
            rec["status"] = "failed"; rec["detail"] = "分析失败/低质，保留点赞，重跑本命令可续做"
            fail_n += 1; failed_now.append(nid)
            log("    ✗ 失败，保留点赞（下次续跑）")
        state["records"].append(rec)
        state["backfill_failed"] = sorted(set(state.get("backfill_failed", [])) | set(failed_now))
        save_json(NEW_TASKS_FILE, state)
        time.sleep(random.uniform(2, 5))
        if limit and analyzed_n + fail_n >= limit:
            log("达到本次新分析上限 %d，停止遍历（已收集的 %d 篇继续执行取消）"
                % (limit, len(pending_unlike)))
            break

    log("分析阶段结束：新分析 %d，已有/跳过 %d，失败 %d，待取消 %d"
        % (analyzed_n, skipped_n, fail_n, len(pending_unlike)))

    # 回到点赞 tab 统一取消
    if pending_unlike:
        log("回到点赞 tab 执行取消（共 %d 篇）..." % len(pending_unlike))
        if not xhs.bootstrap():
            log("无法回到点赞 tab，取消留到下次续跑"); return
        ok_n = 0
        for j, (nid, it, _fp) in enumerate(pending_unlike):
            r = xhs.unlike(nid)
            if r.get("ok"):
                bf_done.add(nid); baseline.add(nid); processed.add(nid)
                state["backfill_done"] = sorted(bf_done)
                state["baseline"] = sorted(baseline)
                state["processed"] = sorted(processed)
                save_json(NEW_TASKS_FILE, state)
                # 同步 A 的取消账本，避免日后重复处理
                prog = load_json(PROGRESS_FILE, {"cancelled": []})
                cs = set(prog.get("cancelled", [])); cs.add(nid)
                prog["cancelled"] = sorted(cs)
                save_json(PROGRESS_FILE, prog)
                ok_n += 1
                log("  回溯取消 [%d/%d] ✓ %s %s" % (j + 1, len(pending_unlike), nid, it.get("title", "")[:24]))
            else:
                log("  回溯取消失败 %s：%s（下次续跑）" % (nid, r.get("msg") or r.get("raw")))
            time.sleep(random.uniform(*UNLIKE_DELAY))
        log("回溯完成：成功取消 %d 篇" % ok_n)
    else:
        log("无需取消（全部失败或已完成）")


# ---------------- 枚举核对 ----------------
def task_enumerate_only(xhs):
    log("===== 只读枚举点赞列表 =====")
    if not xhs.bootstrap():
        log("引导失败"); return
    items = xhs.enumerate_likes(progress_cb=lambda n, hm: log("  已拉取 %d 条 ..." % n) if n % 200 < 80 else None)
    v = sum(1 for x in items if x.get("type") == "video")
    n = len(items) - v
    log("完成：总数 %d | 视频 %d | 图文 %d" % (len(items), v, n))
    log("最新3条：" + " / ".join(x.get("title", "")[:16] for x in items[:3]))
    log("最旧3条：" + " / ".join(x.get("title", "")[:16] for x in items[-3:]))


# ---------------- 任务C：旧信息时效复核（Kimi 联网，独立子进程/独立浏览器会话） ----------------
def task_review_stale():
    log("===== 任务C：旧信息联网时效复核（Kimi，每日≤3篇）=====")
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_stale.py")
    try:
        p = subprocess.run([sys.executable, "-u", script],
                           cwd=os.path.dirname(script), capture_output=True,
                           text=True, encoding="utf-8", timeout=40 * 60)
        for ln in (p.stdout or "").splitlines():
            log("  " + ln)
        if p.returncode != 0:
            log("任务C退出码 %s：%s" % (p.returncode, (p.stderr or "")[-300:]))
    except Exception:
        log("任务C异常：\n" + traceback.format_exc())


# ---------------- 入口 ----------------
def wb_status():
    try:
        p = subprocess.run([WB_EXE, "status"], capture_output=True,
                           text=True, encoding="utf-8", timeout=15)
        lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip().startswith("{")]
        return json.loads(lines[-1]) if lines else {}
    except Exception:
        return {}


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def _chrome_path():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _wb_ext_connected():
    st = wb_status()
    return bool(st.get("running") and st.get("extension_connected")), st


def ensure_webbridge(wait=90):
    """每日自愈：守护没起就拉起 → 等扩展连接；扩展休眠/Chrome 无窗口则唤起 Chrome 再等。"""
    st = wb_status()
    if not st.get("running"):
        log("WebBridge 守护未运行，启动中 ...")
        try:
            subprocess.run([WB_EXE, "start"], capture_output=True,
                           text=True, encoding="utf-8", timeout=30)
        except Exception as e:
            log("WebBridge 启动失败：%s" % str(e)[:150])

    def _poll(secs):
        t0 = time.time()
        while time.time() - t0 < secs:
            ok, s = _wb_ext_connected()
            if ok:
                return s
            time.sleep(3)
        return None

    s = _poll(wait)
    if s:
        log("WebBridge 就绪（扩展已连接 v%s）" % s.get("extension_version", "?"))
        return True
    # 扩展未连：多半是 Chrome 没开窗 / service worker 休眠，主动唤起
    cp = _chrome_path()
    if cp:
        log("扩展未连接，唤起 Chrome 窗口唤醒扩展 ...")
        try:
            subprocess.Popen([cp, "https://www.kimi.com/"])
        except Exception as e:
            log("唤起 Chrome 失败：%s" % str(e)[:120])
        s = _poll(60)
        if s:
            log("WebBridge 就绪（扩展已连接 v%s）" % s.get("extension_version", "?"))
            return True
    log("WebBridge 扩展仍未连接；若本轮环境引导失败，请打开 Chrome 并激活 Kimi WebBridge 扩展")
    return False


def run_round(args, xhs):
    ensure_webbridge()
    if args.enumerate_only:
        task_enumerate_only(xhs); return
    if args.backfill:
        task_backfill(xhs, args.backfill, args.bf_limit); return
    if args.only == "C":
        task_review_stale(); return
    if args.only != "B":
        task_unlike_old(xhs, quota_override=args.quota)
    if args.only != "A":
        try:
            task_process_new(xhs)
        except Exception:
            log("任务B异常：\n" + traceback.format_exc())
    if args.only != "A" and args.only != "B":
        task_review_stale()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["A", "B", "C"])
    ap.add_argument("--session", default=DEFAULT_SESSION)
    ap.add_argument("--quota", type=int, default=None, help="任务A今日取消数（测试用）")
    ap.add_argument("--enumerate-only", action="store_true")
    ap.add_argument("--backfill", type=int, default=0,
                    help="回溯补做：对最近N篇逐个跑v3分析后取消（断点续传）")
    ap.add_argument("--bf-limit", type=int, default=0,
                    help="回溯时本次最多新分析多少篇（0=不限，手动分批用）")
    ap.add_argument("--daemon", action="store_true")
    args = ap.parse_args()

    xhs = XHS(args.session)
    if args.daemon:
        while True:
            try:
                run_round(args, xhs)
            except Exception:
                log("本轮异常：\n" + traceback.format_exc())
            log(">>> 24h 后下一轮")
            time.sleep(24 * 3600 + random.randint(-1800, 1800))
    else:
        run_round(args, xhs)


if __name__ == "__main__":
    main()
