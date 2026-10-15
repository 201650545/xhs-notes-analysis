# -*- coding: utf-8 -*-
"""把 b_answers 的 v3 深度分析同步到飞书多维表格。
   字段：标题/序号/作者/点赞数/链接/内容类型/分类/大类/主题标签/点点总结/
        笔记ID/深度分析全文/存档文件/分析日期
   用法：
     python sync_lark_99.py --check         只生成载荷不写入（首批 99，序号 119 起）
     python sync_lark_99.py                 首批全量写入（顺序固定：点赞页快照顺序）
     python sync_lark_99.py --incremental   增量：只追加表里还没有的笔记ID（每日新增用）
"""
import json, os, subprocess, datetime, sys

BASE = r"D:\Work\小红书点赞分析"
DATA = os.path.join(BASE, "_系统数据")  # 管线 JSON 系统数据（2026-09-28 起统一收纳，勿移出）
ANS = os.path.join(BASE, "b_answers")
CLI = r"C:\Users\郭永涛\.trae-cn\plugins\trae-remote-official\lark\1.0.5\bin\lark-cli.exe"
BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
TABLE_ID = "tblcDvErvsmeynMz"
SEQ_START = 119
BATCH_DATE = datetime.datetime(2026, 9, 23)
VALID_CATS = {"A工具资源", "B技术实操", "C创作设计", "D搞钱变现", "E学习成长", "F视野观点", "G生活其他"}

only_check = "--check" in sys.argv
incremental = "--incremental" in sys.argv

kb_rows = json.load(open(os.path.join(DATA, "_knowledge_base.json"), encoding="utf-8"))["rows"]
kb = {r["id"]: r for r in kb_rows}
snap_list = json.load(open(os.path.join(DATA, "_liked_snapshot.json"), encoding="utf-8"))["items"]
snap = {it["id"]: it for it in snap_list}
full = {it["id"]: it for it in json.load(open(os.path.join(DATA, "_liked_all_full.json"), encoding="utf-8"))["items"]}
tasks = json.load(open(os.path.join(DATA, "_new_tasks.json"), encoding="utf-8"))
rec_ts = {r["id"]: r.get("ts", "") for r in tasks.get("records", [])}


def lark(args, payload):
    pf = os.path.join(DATA, "_lark_sync_tmp.json")
    json.dump(payload, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
    cmd = [CLI, "base"] + args + ["--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
                                  "--json", "@./_lark_sync_tmp.json", "--as", "user", "--format", "json"]
    # cwd 设为 DATA：@./ 相对路径解析到 _系统数据，避免中文目录进命令行参数
    res = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True, encoding="utf-8")
    return json.loads(res.stdout or res.stderr)


def existing_ids_and_maxseq():
    """读表，返回 (已存在笔记ID集合, 当前最大序号)。"""
    j = lark(["+record-list", "--limit", "200", "--format", "json",
              "--field-id", "序号", "--field-id", "笔记ID"], None) if False else None
    # record-list 的过滤参数走命令行，JSON 仅用于复杂过滤；这里直接翻页拉两列
    ids, maxseq, offset = set(), 0, 0
    while True:
        cmd = [CLI, "base", "+record-list", "--base-token", BASE_TOKEN, "--table-id", TABLE_ID,
               "--limit", "200", "--offset", str(offset), "--format", "json", "--as", "user",
               "--field-id", "序号", "--field-id", "笔记ID"]
        res = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding="utf-8")
        d = json.loads(res.stdout or res.stderr)["data"]
        hdr, rows = d["fields"], d["data"]
        ix = {h: i for i, h in enumerate(hdr)}
        for row in rows:
            nid = row[ix["笔记ID"]]
            if nid:
                ids.add(str(nid).strip())
            seq = row[ix["序号"]]
            if isinstance(seq, (int, float)):
                maxseq = max(maxseq, int(seq))
        if not d.get("has_more"):
            break
        offset += len(rows)
        if not rows:
            break
    return ids, maxseq


def build_record(nid, seq, when):
    r = kb[nid]
    fm, sm = full.get(nid, {}), snap.get(nid, {})
    raw = open(os.path.join(ANS, r["file"]), encoding="utf-8").read()
    full_text = "\n".join(raw.splitlines()[3:]).strip()
    ntype = "视频" if (fm.get("type") == "视频" or r["type"] == "视频") else "笔记"
    rec = {
        "标题": r["title"], "序号": seq,
        "作者": fm.get("author") or sm.get("author") or r["author"],
        "点赞数": str(fm.get("like", "")).strip(),
        "链接": fm.get("href") or r["url"],
        "内容类型": [ntype], "分类": ["小红书点赞分析"],
        "主题标签": " ".join("#" + t for t in r["tags"]),
        "点点总结": r["summary"], "笔记ID": nid,
        "深度分析全文": full_text, "存档文件": r["file"],
        "分析日期": int(when.timestamp() * 1000),
    }
    # 大类：仅写入合法选项；自动分类的粗类目不写，避免污染选项
    if r["category"] in VALID_CATS:
        rec["大类"] = [r["category"]]
    return rec


if incremental:
    have, maxseq = existing_ids_and_maxseq()
    todo = [i for i in kb if i not in have]
    # 新增按分析处理时间升序追加
    todo.sort(key=lambda i: rec_ts.get(i, ""))
    when = datetime.datetime.now()
    records = [build_record(i, maxseq + n, when) for n, i in enumerate(todo, 1)]
    untagged = [kb[i]["title"] for i in todo if kb[i]["category"] not in VALID_CATS]
    print("表内已有:", len(have), "最大序号:", maxseq, "待追加:", len(records))
    if untagged:
        print("提醒：%d 篇缺人工大类/标签，已留空待补:" % len(untagged))
        for t in untagged:
            print("  -", t)
else:
    # 首批固定顺序：点赞页快照顺序（最近在前），快照外按处理时间排末尾
    ordered = [it["id"] for it in snap_list if it["id"] in kb]
    rest = sorted((i for i in kb if i not in set(ordered)), key=lambda i: rec_ts.get(i, ""))
    ordered += rest
    assert len(ordered) == 99, len(ordered)
    records = [build_record(i, SEQ_START + n, BATCH_DATE) for n, i in enumerate(ordered)]
    print("首批记录数:", len(records))

payload = {"create_records": records}
pf = os.path.join(BASE, "_lark_payload_99.json")
json.dump(payload, open(pf, "w", encoding="utf-8"), ensure_ascii=False)
print("载荷字节:", os.path.getsize(pf))

if only_check or not records:
    sys.exit(0)

j = lark(["+record-batch-create"], payload)
print("ok:", j.get("ok"))
if j.get("ok"):
    print("created:", len(j.get("data", {}).get("record_id_list", [])))
else:
    print(json.dumps(j.get("error", j), ensure_ascii=False)[:800])
