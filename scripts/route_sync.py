# -*- coding: utf-8 -*-
"""行动路由 + 单条入库（GPT 七步法的第 2、7 步）

职责：
  1) parse_routing()  从点点对 ROUTE_PROMPT 的答复里解析出结构化路由
  2) write_lark()     把单条新笔记（含路由字段）追加进飞书表，人工已拍板=否 → 进「01 待拍板」
  3) save_route()     路由落盘到 _routing.json（不改动 b_answers 正文，避免污染一句话总结抽取）

用法：
  python route_sync.py --check <笔记ID>    只解析本地已有路由并打印入库载荷，不写表
"""
import os, re, sys, json, subprocess, datetime

BASE = r"D:\Work\小红书点赞分析"
DATA = os.path.join(BASE, "_系统数据")  # 管线 JSON 系统数据（2026-09-28 起统一收纳，勿移出）
ANS = os.path.join(BASE, "b_answers")
ROUTE_FILE = os.path.join(DATA, "_routing.json")
LARK_MAP_FILE = os.path.join(DATA, "_lark_map.json")
REVIEW_STATE_FILE = os.path.join(DATA, "_review_state.json")
FULL_FILE = os.path.join(DATA, "_liked_all_full.json")
SNAP_FILE = os.path.join(DATA, "_liked_snapshot.json")

TIER_LARK = {"sensitive": "高（福利/版本类）", "normal": "低（长期有效类）"}
VERDICT_BADGE = {"有效": "✅ 仍有效", "已失效": "❌ 已失效", "已升级": "⬆️ 已升级",
                 "无法核实": "❓ 未能核实"}
CLI = r"C:\Users\郭永涛\.trae-cn\plugins\trae-remote-official\lark\1.0.5\bin\lark-cli.exe"
BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
TABLE_ID = "tblcDvErvsmeynMz"

ROUTE_KEYS = ["路由", "处理意图", "优先级", "时效", "行动成本",
              "最小下一步", "复刻目标", "核心知识", "路由理由"]

INTENT_OK = {"复刻", "学习", "灵感", "跟踪", "仅了解", "不处理"}
PRIO_OK = {"P0 尽快", "P1 本周", "P2 以后", "P3 资料"}
PRIO_DAYS = {"P0 尽快": 1, "P1 本周": 3, "P2 以后": 14, "P3 资料": None}


def _norm(s):
    return re.sub(r"[\s*#`]+", "", (s or "").strip())


def parse_routing(text):
    """把'键：值'形式的答复解析成 dict；解析不到关键项返回 None。"""
    if not text:
        return None
    out = {}
    for raw in text.replace("\r", "").split("\n"):
        ln = raw.strip().strip("*# ").strip()
        m = re.match(r"^([\u4e00-\u9fa5A-Za-z0-9]{2,6})\s*[：:]\s*(.+)$", ln)
        if not m:
            continue
        k, v = _norm(m.group(1)), m.group(2).strip()
        for want in ROUTE_KEYS:
            if k == want and want not in out:
                out[want] = v
                break
    if "路由" not in out:
        return None
    out["_raw"] = text.strip()
    return out


def _pick(route, table, default=None):
    """从'复刻闭环 或 学习闭环 或 归档观察'这类答复里挑出第一个命中项。"""
    s = route.get("路由", "")
    for k in table:
        if k in s:
            return k
    return default


def to_fields(route, today=None):
    """路由 → 飞书字段（只含路由相关字段）。"""
    today = today or datetime.date.today()
    f = {"人工已拍板": False}
    if not route:
        f.update({"处理意图": ["仅了解"], "复刻状态": ["不适用"], "学习状态": ["不适用"]})
        return f

    r = _pick(route, ["复刻闭环", "学习闭环", "归档观察"], "归档观察")
    intent = _norm(route.get("处理意图", ""))
    if intent not in INTENT_OK:
        intent = {"复刻闭环": "复刻", "学习闭环": "学习", "归档观察": "仅了解"}[r]
    f["处理意图"] = [intent]

    if r == "复刻闭环":
        f["复刻状态"], f["学习状态"] = ["待评估"], ["不适用"]
    elif r == "学习闭环":
        f["复刻状态"], f["学习状态"] = ["不适用"], ["待理解"]
    else:
        f["复刻状态"], f["学习状态"] = ["不适用"], ["不适用"]

    prio = _norm(route.get("优先级", ""))
    for k in PRIO_OK:
        if _norm(k) == prio or k in route.get("优先级", ""):
            f["我的优先级"] = [k]
            days = PRIO_DAYS[k]
            if days:
                f["下次处理日期"] = int(
                    (datetime.datetime.combine(today + datetime.timedelta(days=days),
                                               datetime.time(9, 0))).timestamp() * 1000)
            break

    if route.get("最小下一步"):
        f["下一步动作"] = route["最小下一步"][:500]
    kh = route.get("核心知识")
    if kh and _norm(kh) not in ("无", "不适用", "无。"):
        f["AI核心知识"] = kh[:500]
    return f


def save_route(nid, route):
    data = {}
    if os.path.exists(ROUTE_FILE):
        try:
            data = json.load(open(ROUTE_FILE, encoding="utf-8"))
        except Exception:
            data = {}
    data[nid] = route or {}
    json.dump(data, open(ROUTE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_route(nid):
    if not os.path.exists(ROUTE_FILE):
        return None
    return json.load(open(ROUTE_FILE, encoding="utf-8")).get(nid)


# ---------------- 飞书写入 ----------------
def _lark(args, payload):
    pf = os.path.join(DATA, "_lark_route_tmp.json")
    json.dump(payload, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
    cmd = [CLI, "base"] + args + ["--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
                                  "--json", "@./_lark_route_tmp.json", "--as", "user"]
    # cwd 设为 DATA：@./ 相对路径解析到 _系统数据，避免中文目录进命令行参数
    res = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(res.stdout or res.stderr)
    except Exception:
        return {"ok": False, "raw": (res.stdout or res.stderr)[:400]}


def _meta(nid):
    for path in (FULL_FILE, SNAP_FILE):
        if not os.path.exists(path):
            continue
        try:
            items = json.load(open(path, encoding="utf-8"))["items"]
        except Exception:
            continue
        for it in items:
            if it.get("id") == nid:
                return it
    return {}


def max_seq():
    ids, mx, offset = set(), 0, 0
    while True:
        cmd = [CLI, "base", "+record-list", "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
               "--limit", "200", "--offset", str(offset), "--format", "json", "--as", "user",
               "--field-id", "序号", "--field-id", "笔记ID"]
        res = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8")
        d = json.loads(res.stdout or res.stderr)["data"]
        hdr, rows = d["fields"], d["data"]
        ix = {h: i for i, h in enumerate(hdr)}
        for row in rows:
            if row[ix["笔记ID"]]:
                ids.add(str(row[ix["笔记ID"]]).strip())
            if isinstance(row[ix["序号"]], (int, float)):
                mx = max(mx, int(row[ix["序号"]]))
        if not d.get("has_more") or not rows:
            break
        offset += len(rows)
    return ids, mx


def build_payload(nid, title, href, ans, route, when=None, it=None):
    """组装单条入库载荷（扁平 {字段名:值}）。it = 点赞列表条目（含 author/type/token）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_knowledge import extract_summary  # 复用一句话总结抽取

    when = when or datetime.datetime.now()
    meta = dict(_meta(nid))
    if it:
        for k in ("author", "type", "title", "token", "like"):
            if it.get(k) and not meta.get(k):
                meta[k] = it[k]
    ntype = "视频" if meta.get("type") in ("视频", "video") else "笔记"
    body = ans or ""
    rec = {
        "标题": title or meta.get("title", ""),
        "作者": meta.get("author", ""),
        "点赞数": str(meta.get("like", "") or "").strip(),
        "链接": href or meta.get("href", ""),
        "内容类型": [ntype],
        "分类": ["小红书点赞分析"],
        "主题标签": "", "大类": [],
        "点点总结": extract_summary(body),
        "笔记ID": nid,
        "深度分析全文": body,
        "存档文件": "%s.txt" % nid,
        "分析日期": int(when.timestamp() * 1000),
    }
    rec.update(to_fields(route, today=when.date()))
    return rec


def write_lark(nid, title, href, ans, route, when=None, it=None):
    """追加一条记录，返回 record_id（失败抛异常）。"""
    have, mx = max_seq()
    if nid in have:
        return "exists"
    rec = build_payload(nid, title, href, ans, route, when, it)
    rec["序号"] = mx + 1
    j = _lark(["+record-batch-create"], {"create_records": [rec]})
    if not j.get("ok"):
        raise RuntimeError("lark 写入失败: " + json.dumps(j.get("error", j), ensure_ascii=False)[:300])
    ids = j.get("data", {}).get("record_id_list") or []
    if ids:
        m = load_map()
        m[nid] = ids[0]
        save_map(m)
    return ids[0] if ids else "ok"


# ---------------- 时效复核镜像（本地 -> 飞书单向上行） ----------------
def load_map():
    if os.path.exists(LARK_MAP_FILE):
        try:
            return json.load(open(LARK_MAP_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_map(m):
    json.dump(m, open(LARK_MAP_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def refresh_map():
    """全量翻页拉取 {笔记ID: record_id}。"""
    m, offset = {}, 0
    while True:
        cmd = [CLI, "base", "+record-list", "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
               "--limit", "200", "--offset", str(offset), "--format", "json", "--as", "user",
               "--field-id", "笔记ID"]
        res = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8")
        d = json.loads(res.stdout or res.stderr)["data"]
        for rid, row in zip(d["record_id_list"], d["data"]):
            if row and row[0]:
                m[str(row[0]).strip()] = rid
        if not d.get("has_more") or not d["data"]:
            break
        offset += len(d["data"])
    save_map(m)
    return m


def _answer_body(nid):
    p = os.path.join(ANS, "%s.txt" % nid)
    if not os.path.exists(p):
        return ""
    return "\n".join(open(p, encoding="utf-8").read().splitlines()[3:]).strip()


def _ms(date_s):
    return int(datetime.datetime.combine(
        datetime.date.fromisoformat(date_s), datetime.time(9, 0)).timestamp() * 1000)


def build_review_text(n, body):
    """飞书版'深度分析全文'：复核结论置顶 + 原分析全文（镜像 Obsidian 呈现，纯文本版）。"""
    h = (n.get("history") or [{}])[0]
    v = h.get("verdict", "")
    head = ["🔎 联网复核（%s）：%s" % (h.get("date", n.get("checked_at", "")),
                                  VERDICT_BADGE.get(v, v))]
    if v == "已升级" and h.get("new_summary"):
        head.append("【最新结论】" + h["new_summary"])
    if h.get("facts"):
        head.append("【现状】" + h["facts"])
    if h.get("changes") and h.get("changes") != "无":
        head.append("【变化】" + h["changes"])
    if h.get("sources"):
        head.append("【来源】" + h["sources"])
    head.append("下次复核：%s" % n.get("next_review", ""))
    head.append("━" * 20)
    head.append("📄 以下为入库时的原始分析%s" % (
        "（信息已过时，以顶部复核结论为准）" if v in ("已失效", "已升级") else ""))
    return "\n".join(x for x in head if x) + "\n\n" + body


def push_reviews(nids=None, _st=None):
    """把复核状态单向上行到飞书。nids=None 推送所有已核查笔记。返回更新条数。"""
    st = _st or json.load(open(REVIEW_STATE_FILE, encoding="utf-8"))
    notes = st["notes"]
    if nids is None:
        nids = [k for k, n in notes.items() if n.get("checked_at")]
    nids = [i for i in nids if notes.get(i, {}).get("checked_at")]
    if not nids:
        return 0
    m = load_map()
    if any(i not in m for i in nids):
        m = refresh_map()
    obj, skip = {}, []
    for i in nids:
        rid = m.get(i)
        if not rid:
            skip.append(i)
            continue
        n = notes[i]
        f = {"信息状态": [n["status"]],
             "时效分级": [TIER_LARK.get(n.get("tier"), "低（长期有效类）")],
             "复核日期": _ms(n["next_review"]),
             "最近核实": _ms(n["checked_at"])}
        h = (n.get("history") or [{}])[0]
        if h.get("verdict") == "已升级" and h.get("new_summary"):
            f["点点总结"] = h["new_summary"]
        f["深度分析全文"] = build_review_text(n, _answer_body(i))
        obj[rid] = f
    if not obj:
        return 0
    j = _lark(["+record-batch-update"], {"update_records": obj})
    if not j.get("ok"):
        raise RuntimeError("lark 复核回写失败: " + json.dumps(j.get("error", j), ensure_ascii=False)[:300])
    if skip:
        print("无飞书映射，跳过 %d 篇: %s" % (len(skip), ",".join(skip[:5])))
    return len(obj)


if __name__ == "__main__":
    if "--review-push" in sys.argv:
        ids = None
        if "--ids" in sys.argv:
            ids = sys.argv[sys.argv.index("--ids") + 1].split(",")
        print("推送复核结果到飞书：%d 篇" % push_reviews(ids))
    elif "--refresh-map" in sys.argv:
        m = refresh_map()
        print("映射已刷新：%d 条" % len(m))
    elif "--check" in sys.argv:
        nid = sys.argv[sys.argv.index("--check") + 1]
        rt = load_route(nid)
        rp = os.path.join(ANS, "%s.txt" % nid)
        ans = ""
        if os.path.exists(rp):
            ans = "\n".join(open(rp, encoding="utf-8").read().splitlines()[3:]).strip()
        print("路由:", json.dumps(rt, ensure_ascii=False, indent=1))
        print("字段:", json.dumps(to_fields(rt), ensure_ascii=False, indent=1))
        print("载荷:", json.dumps(build_payload(nid, "", "", ans, rt), ensure_ascii=False)[:900])