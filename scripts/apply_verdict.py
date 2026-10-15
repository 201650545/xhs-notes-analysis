# -*- coding: utf-8 -*-
"""二审判决执行器：把判决台导出的 verdict_<批次>_final.json 落到《笔记筛选规范》§5 的四处。

默认 dry-run：只校验＋出预览（写 md），一个字节都不改。加 --apply 才真删/真留。
争议篇（reason 里带「｜只留：」）判删时按元规则「笔记可删、案例可留」先提炼进保留_案例与方法.md 再删原文。

用法：
  python scripts/apply_verdict.py --batch 20260929            # 校验并写预览
  python scripts/apply_verdict.py --batch 20260929 --apply    # 执行
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "_系统数据")
COCKPIT = os.path.join(BASE, "00_项目驾驶舱_可视化中心")
ANSWERS = os.path.join(BASE, "b_answers")
LARK_EXE = r"C:\Users\郭永涛\.trae-cn\plugins\trae-remote-official\lark\1.0.5\bin\lark-cli.exe"
LARK_BASE_TOKEN = "StmDbTXQWaujshs9NpIc3UFpnAc"
LARK_TABLE_ID = "tblcDvErvsmeynMz"
LARK_CHUNK = 44  # SKILL.md §3：Windows 命令行长度上限，每批 ≤44 个 --record-id
TODAY = time.strftime("%Y-%m-%d")


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jdump(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=2)


def read_batch(batch):
    p = os.path.join(DATA, "review_batch_%s.tsv" % batch)
    if not os.path.exists(p):
        raise SystemExit("[exec] 批次一审文件缺失：%s —— 判决无法对应一审理由，拒执行" % p)
    out = {}
    with open(p, encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("\t")
        for line in f:
            if not line.strip():
                continue
            cells = line.rstrip("\n").split("\t")
            out[cells[0]] = dict(zip(head, cells))
    return out


def link_of(nid):
    p = os.path.join(ANSWERS, nid + ".txt")
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for ln in lines[:6]:
        if ln.startswith("http"):
            return ln
    return ""


def triad(ids, ledger, mapping):
    miss = []
    for i in ids:
        gaps = []
        if i not in ledger:
            gaps.append("台账无")
        if i not in mapping:
            gaps.append("映射无")
        if not os.path.exists(os.path.join(ANSWERS, i + ".txt")):
            gaps.append("全文无")
        if gaps:
            miss.append((i, gaps))
    return miss


def curated_ids():
    """精选库里已收录的笔记 ID（七大类批次升级那 11 篇的行动台账随结业清空，全文留架属预期）"""
    p = os.path.join(COCKPIT, "精选保留库.md")
    if not os.path.exists(p):
        return set()
    return set(re.findall(r"笔记ID：`([0-9a-f]{24})`", open(p, encoding="utf-8").read()))


def orphans(ledger, mapping):
    files = {fn[:-4] for fn in os.listdir(ANSWERS) if fn.endswith(".txt")}
    cur = curated_ids()
    no_ledger = sorted(files - set(ledger))
    return {
        "台账有全文缺": sorted(set(ledger) - files),
        "映射有全文缺": sorted(set(mapping) - files),
        "全文有台账缺·预期(精选库升级篇)": sorted(i for i in no_ledger if i in cur),
        "全文有台账缺·异常": sorted(i for i in no_ledger if i not in cur),
        "映射值非rec开头": sorted(k for k, v in mapping.items() if not str(v).startswith("rec")),
    }


def next_num(md_path, pat):
    if not os.path.exists(md_path):
        return 1
    ns = [int(m.group(1)) for m in re.finditer(pat, open(md_path, encoding="utf-8").read(), re.M)]
    return max(ns) + 1 if ns else 1


def case_of(reason):
    i = reason.find("｜只留：")
    return re.sub(r"\s+", " ", reason[i + 4:]).strip() if i >= 0 else ""


def rule_of(reason):
    m = re.match(r"【(.+?)】", reason or "")
    return m.group(1) if m else ""


def body_of(reason):
    return re.sub(r"^【.+?】", "", reason or "").split("｜只留：")[0].strip()


def lark_delete(recids):
    """云端先删、本地后删（SKILL.md §3）；每批 ≤44，任一批不回显 ok 立即停。"""
    if not recids:
        return 0, "无飞书行需删"
    for i in range(0, len(recids), LARK_CHUNK):
        chunk = recids[i:i + LARK_CHUNK]
        cmd = [LARK_EXE, "base", "+record-delete", "--base-token", LARK_BASE_TOKEN,
               "--table-id", LARK_TABLE_ID, "--as", "user", "--yes"]
        for r in chunk:
            cmd += ["--record-id", r]
        p = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True, encoding="utf-8")
        out = ((p.stdout or "") + (p.stderr or "")).replace(" ", "")
        if '"ok":true' not in out:
            return i, "第 %d 批失败即停（本地未动，可重跑）：%s" % (i // LARK_CHUNK + 1, out[:300])
    return len(recids), "飞书 %d 行已删" % len(recids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    vp = os.path.join(DATA, "verdicts", "verdict_%s_final.json" % args.batch)
    if not os.path.exists(vp):
        print("[exec] 判决文件不在规定路径：%s" % vp)
        return 3
    v = jload(vp)
    if v.get("kind") != "second_review_verdict" or v.get("batch") != args.batch or v.get("demo"):
        print("[exec] 判决文件非本批正式批次（kind/batch/demo 不符），拒执行")
        return 3
    batch = read_batch(args.batch)
    ledger = jload(os.path.join(DATA, "_routing.json"))
    mapping = jload(os.path.join(DATA, "_lark_map.json"))

    keep = [i for i in v.get("keep", []) if i in batch]
    drop = [i for i in v.get("drop", []) if i in batch]
    pending = v.get("pending", [])
    stray = [i for i in (v.get("keep", []) + v.get("drop", [])) if i not in batch]
    cases = [(i, case_of(batch[i]["reason"])) for i in drop if case_of(batch[i]["reason"])]

    problems = []
    for tag, ids in (("留", keep), ("删", drop)):
        for nid, gaps in triad(ids, ledger, mapping):
            problems.append("%s侧 %s：%s" % (tag, nid, "、".join(gaps)))
    # SKILL.md §1/§2：ID 一律从判决文件取（不手抄），但长度与字符集要在 dry-run 就断住
    bad_id = [i for i in keep + drop if len(i) != 24 or any(c not in "0123456789abcdef" for c in i)]
    if bad_id:
        problems.append("ID 非 24 位 hex：%s" % bad_id[:5])
    recs_drop = [mapping[i] for i in drop if i in mapping]
    if len(recs_drop) != len(set(recs_drop)):
        problems.append("判删篇的飞书 recID 有重复，集合校验不过")
    orph = orphans(ledger, mapping)

    L = []
    L.append("# 二审执行 %s（%s，%s）" % (args.batch, TODAY, "APPLY 已执行" if args.apply else "DRY-RUN 预览，未改任何数据"))
    L.append("")
    L.append("- 判决文件：`_系统数据/verdicts/verdict_%s_final.json`（导出于 %s）" % (args.batch, v.get("exported_at", "?")))
    L.append("- 分布：留 %d｜删 %d｜未判不动 %d｜不在本批的陌生 ID %d" % (len(keep), len(drop), len(pending), len(stray)))
    L.append("- 走「笔记可删、案例可留」的争议篇：%d 篇" % len(cases))
    L.append("")
    L.append("## 一、校验")
    L.append("")
    if problems:
        L.append("**三件不齐（台账/映射/全文）%d 条，需先补或改判：**" % len(problems))
        for x in problems:
            L.append("- %s" % x)
    else:
        L.append("- 留删两侧共 %d 篇的「台账 / 飞书映射 / 分析全文」三件齐全 ✔" % (len(keep) + len(drop)))
    L.append("- 孤儿扫描：台账有全文缺 %d｜映射有全文缺 %d｜全文有台账缺（其中精选库升级篇 %d 属预期，异常 %d）｜映射值非 rec 开头 %d"
             % (len(orph["台账有全文缺"]), len(orph["映射有全文缺"]),
                len(orph["全文有台账缺·预期(精选库升级篇)"]), len(orph["全文有台账缺·异常"]),
                len(orph["映射值非rec开头"])))
    if orph["全文有台账缺·异常"] or orph["台账有全文缺"] or orph["映射有全文缺"] or orph["映射值非rec开头"]:
        problems.append("存在异常孤儿：%s" % {k: v for k, v in orph.items() if v and "预期" not in k})
    if stray:
        L.append("- ⚠️ 判决里有本批不认识的 ID：%s" % stray[:8])
    L.append("")
    L.append("## 二、判留 %d 篇（进精选保留库）" % len(keep))
    for i in keep:
        r = batch[i]
        L.append("- `%s` %s ｜判据：%s ｜理由：%s" % (i, r["title"], rule_of(r["reason"]) or "—", body_of(r["reason"])[:90]))
    L.append("")
    L.append("## 三、判删 %d 篇（四处同步真删，不留存档）" % len(drop))
    for i in drop:
        r = batch[i]
        L.append("- `%s` %s ｜判据：%s ｜%s" % (i, r["title"], rule_of(r["reason"]) or "—", body_of(r["reason"])[:90]))
    L.append("")
    if cases:
        L.append("## 四、先提炼再删（案例进保留_案例与方法.md）")
        for i, c in cases:
            L.append("- `%s` %s → %s" % (i, batch[i]["title"], c[:160]))
        L.append("")
    if pending:
        L.append("> 未判 %d 篇一律不动，下次刷新判决台从首张未判继续。" % len(pending))
        L.append("")
    preview = os.path.join(COCKPIT, "二审执行_%s.md" % args.batch)
    with open(preview, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L[:14]))
    print("[exec] 预览 → %s" % preview)

    if not args.apply:
        print("[exec] DRY-RUN 结束。确认无误后加 --apply 才真删。")
        return 1 if problems else 0

    if problems:
        print("[exec] 有 %d 条三件不齐，拒执行——先解决再 --apply" % len(problems))
        return 1

    # 云端先删、本地后删：云端失败时本地还在，可重跑（SKILL.md §3）
    done, msg = lark_delete(recs_drop)
    print("[exec] " + msg)
    if done != len(recs_drop):
        print("[exec] 云端未删净，本地一律不动，修好再重跑")
        return 1

    n = next_num(os.path.join(COCKPIT, "精选保留库.md"), r"^### (\d+)\.", )
    new_entries = []
    for i in keep:
        r = batch[i]
        new_entries.append("\n### %d. %s\n- 笔记ID：`%s`\n- 全文：[b_answers/%s.txt](file:///%s/b_answers/%s.txt)\n- 原链接：%s\n- **为什么留**：%s（二审判决 %s）\n"
                           % (n, r["title"], i, i, BASE.replace("\\", "/"), i, link_of(i),
                              body_of(r["reason"]) or r["what"], TODAY))
        if i in ledger:
            ledger[i]["保留"] = True
            ledger[i]["保留时间"] = TODAY
            ledger[i]["保留原因"] = "%s（二审判决，判据 %s）" % (body_of(r["reason"]) or r["what"], rule_of(r["reason"]) or "—")
        n += 1
    if new_entries:
        sp = os.path.join(COCKPIT, "精选保留库.md")
        s = open(sp, encoding="utf-8").read()
        s = re.sub(r"精选篇数: \d+", "精选篇数: %d" % (n - 1), s)
        s = re.sub(r"案例数: \d+", "案例数: %d" % next_num(os.path.join(COCKPIT, "保留_案例与方法.md"), r"^## 案例 (\d+)"), s)
        s = re.sub(r"更新日期: [0-9-]+", "更新日期: %s" % TODAY, s)
        open(sp, "w", encoding="utf-8").write(s.rstrip("\n") + "\n" + "".join(new_entries))

    if cases:
        cn = next_num(os.path.join(COCKPIT, "保留_案例与方法.md"), r"^## 案例 (\d+)")
        txt = ""
        for i, c in cases:
            txt += ("\n---\n\n## 案例 %02d｜%s\n\n（源笔记 `%s`《%s》，二审判删原文；判据：笔记可删、案例可留）\n\n%s\n\n"
                    "**明确不保留的**：原笔记其余部分随判决四处真删\n" % (cn, c[:28], i, batch[i]["title"], c))
            cn += 1
        with open(os.path.join(COCKPIT, "保留_案例与方法.md"), "a", encoding="utf-8") as f:
            f.write(txt)

    for i in drop:
        p = os.path.join(ANSWERS, i + ".txt")
        if os.path.exists(p):
            os.remove(p)
        ledger.pop(i, None)
        mapping.pop(i, None)
    jdump(os.path.join(DATA, "_routing.json"), ledger)
    jdump(os.path.join(DATA, "_lark_map.json"), mapping)

    # §5 终检（真删完立刻自检，不留到下次）
    files = {fn[:-4] for fn in os.listdir(ANSWERS) if fn.endswith(".txt")}
    final = []
    if set(mapping) - files:
        final.append("映射有全文缺 %d" % len(set(mapping) - files))
    if mapping and not set(mapping) <= files:
        final.append("映射与全文集合不等")
    if [k for k, v in mapping.items() if not str(v).startswith("rec")]:
        final.append("映射值非 rec 开头")
    for i in keep:
        if not os.path.exists(os.path.join(ANSWERS, i + ".txt")):
            final.append("判留篇全文缺 %s" % i)
    print("[exec] 本地四处已改：删 %d 篇全文/台账/映射，留 %d 篇进精选，提炼案例 %d"
          % (len(drop), len(keep), len(cases)))
    print("[exec] 终检：" + ("；".join(final) if final else "映射⊆全文 ✔ rec 前缀 ✔ 判留全文在架 ✔")
          + "｜现存 全文%d 映射%d 台账%d" % (len(files), len(mapping), len(ledger)))
    print("[exec] 未判 %d 篇不动" % len(pending))
    return 1 if final else 0


if __name__ == "__main__":
    sys.exit(main())
