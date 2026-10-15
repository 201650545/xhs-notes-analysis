# -*- coding: utf-8 -*-
"""把 b_answers 的 99 篇 v3 分析结构化为知识库：
   提取 标题/链接/类型/作者/大类/一句话总结/全文 -> _knowledge_base.json
   （主题标签由人工/模型在 _tags_review.json 回填后再合入）
"""
import os, re, json, datetime, sys

BASE = r"<PROJECT_DIR>"
DATA = os.path.join(BASE, "_系统数据")  # 管线 JSON 系统数据（2026-09-28 起统一收纳，勿移出）
ANS = os.path.join(BASE, "b_answers")
SNAP = os.path.join(DATA, "_liked_snapshot.json")
TASKS = os.path.join(DATA, "_new_tasks.json")
KB = os.path.join(DATA, "_knowledge_base.json")
MD = os.path.join(BASE, "知识库_点赞笔记.md")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_final  # 复用 classify

HEAD_RE = re.compile(r"^\s*([一二三四五六七八九十]+)[、.．]\s*(.+?)\s*$")
CN_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,
          "十一":11,"十二":12}


def split_sections(body):
    """按 中文数字标题 切章节，返回 [(标题, 正文)]。"""
    secs, cur_h, cur_b = [], None, []
    for ln in body.splitlines():
        m = HEAD_RE.match(ln.strip())
        if m and CN_NUM.get(m.group(1)):
            if cur_h is not None:
                secs.append((cur_h, "\n".join(cur_b).strip()))
            cur_h, cur_b = m.group(2).strip(), []
        else:
            if cur_h is not None:
                cur_b.append(ln)
    if cur_h is not None:
        secs.append((cur_h, "\n".join(cur_b).strip()))
    return secs


# AI 客套话/追问尾巴（出现即截断）
TAIL_RE = re.compile(
    r"(?:\s{2,}|[。；;])\s*(?:补充一点|补充说明|联网补充|如果你需要|如果你打算|如果你也|你目前是在|等仓库公开|"
    r"我可以帮你|需要的话|感兴趣的话|建议先|不过评论|评论区有人|从评论区|根据(?:联网)?搜索|根据站内|"
    r"另外，?我|如(?:果|需)需要|你提到|你说的|你想(?:直接|了解)|想看|想知道|先说结论|说明：|注：)")
# 章节内"关键点"内嵌标记（出现则只保留标记之后）
KEY_MARK_RE = re.compile(r"(?:一句话总结)?最(?:该|值得)(?:记住|收藏)的?关键点?[:：]?")
SUMM_MARK_RE = re.compile(r"一句话总结(?:最值得收藏的点)?[:：]?")

CAT_NAMES = {
    "A": "A工具资源", "B": "B技术实操", "C": "C创作设计",
    "D": "D搞钱变现", "E": "E学习成长", "F": "F视野观点", "G": "G生活其他",
}


def clean_summary(s):
    """截掉 AI 客套尾巴 + 提取内嵌"关键点"句。"""
    s = s.strip()
    marks = list(KEY_MARK_RE.finditer(s))
    if marks:
        tail = marks[-1].end()
        rest = s[tail:].strip("：: \n")
        if len(rest) >= 20:
            s = rest
    m = SUMM_MARK_RE.search(s)
    if m and m.start() > 0:
        rest = s[m.end():].strip("：: \n")
        if len(rest) >= 20:
            s = rest
    cut = TAIL_RE.search(s)
    if cut:
        s = s[:cut.start()].strip()
    return s[:500].strip()


def extract_summary(body):
    secs = split_sections(body)
    # 优先最后一个标题含"总结"的章节
    summ = [b for h, b in secs if "总结" in h]
    if summ:
        return clean_summary(summ[-1])
    # 兜底：核心知识点/核心观点 章节
    for key in ("核心知识点", "核心观点"):
        for h, b in secs:
            if h.startswith(key):
                return clean_summary(b[:400])
    # 再兜底：正文最后 260 字
    plain = re.sub(r"\s+", "", body)
    return clean_summary(plain[-260:])


def main():
    snap = {it["id"]: it for it in json.load(open(SNAP, encoding="utf-8"))["items"]}
    tasks = json.load(open(TASKS, encoding="utf-8"))
    rec_meta = {r["id"]: r for r in tasks.get("records", [])}

    # 人工大类/标签覆盖
    ov_file = os.path.join(DATA, "_tags_override.json")
    overrides = json.load(open(ov_file, encoding="utf-8")) if os.path.exists(ov_file) else {}

    rows = []
    for fn in sorted(os.listdir(ANS)):
        if not fn.endswith(".txt"):
            continue
        nid = fn[:-4]
        raw = open(os.path.join(ANS, fn), encoding="utf-8").read()
        lines = raw.splitlines()
        title = next((l.lstrip("# ").strip() for l in lines[:4]
                      if l.strip() and not l.startswith("# v3") and "xiaohongshu.com" not in l), nid)
        url = next((l.lstrip("# ").strip() for l in lines[:5] if "xiaohongshu.com" in l), "")
        # 正文：去掉前3行头
        body = "\n".join(lines[3:]).strip()
        meta = snap.get(nid, {})
        ntype = "视频" if meta.get("type") == "video" else "笔记"
        author = meta.get("author", "")
        ov = overrides.get(nid)
        cat = CAT_NAMES.get(ov["cat"], batch_final.classify(title)) if ov else batch_final.classify(title)
        tags = ov["tags"] if ov else []
        summary = extract_summary(body)
        rows.append({
            "id": nid,
            "title": title,
            "url": url,
            "type": ntype,
            "author": author,
            "category": cat,                    # A工具资源/B技术实操/...
            "tags": tags,
            "summary": summary,
            "full_len": len(body),
            "file": fn,
            "status": rec_meta.get(nid, {}).get("status", ""),
        })

    rows.sort(key=lambda r: (r["category"], r["title"]))
    json.dump({"generated_at": datetime.datetime.now().isoformat(),
               "count": len(rows), "rows": rows},
              open(KB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 输出标注清单（id/标题/大类/标签/摘要），供复核
    review = [{"id": r["id"], "title": r["title"], "category": r["category"],
               "tags": r["tags"], "summary": r["summary"]} for r in rows]
    json.dump(review, open(os.path.join(DATA, "_tags_review.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    from collections import Counter
    print("总数:", len(rows))
    print("大类分布:", dict(Counter(r["category"] for r in rows)))
    print("已带标签:", sum(1 for r in rows if r["tags"]))
    print("无摘要兜底(短):", sum(1 for r in rows if len(r["summary"]) < 80))

    # 生成问答用 Markdown 总览（每条含定位信息 + 一句话总结 + 全文文件路径）
    lines = ["# 小红书点赞笔记知识库（v3 深度分析索引）", "",
             f"- 条数：{len(rows)}　生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}",
             "- 回答用户问题时：先按标题/标签/一句话总结定位条目，需要细节再打开 `b_answers/<笔记ID>.txt` 读全文",
             "- 飞书多维表格同步保存同样数据（字段：深度分析全文/大类/主题标签 等）", ""]
    cur = None
    for r in rows:
        if r["category"] != cur:
            cur = r["category"]
            lines += ["", f"## {cur}", ""]
        tags = " ".join("#" + t for t in r["tags"])
        lines += [
            f"### {r['title']}",
            f"- 类型：{r['type']}　作者：{r['author'] or '未知'}　标签：{tags}",
            f"- 笔记ID：`{r['id']}`　全文：`b_answers/{r['file']}`",
            f"- 链接：{r['url']}",
            f"- 一句话总结：{r['summary']}", ""]
    with open(MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("知识库:", KB)
    print("总览:", MD)


if __name__ == "__main__":
    main()
