# -*- coding: utf-8 -*-
"""二审·网关判定器（judge_gateway.py）
把同一批笔记+同一套 §4 校准判据 POST 到本地网关 :3100 的指定编排线，逐篇拿 verdict JSON。
用法：
  python judge_gateway.py --ids 6a...,6a...            # 指定笔记
  python judge_gateway.py --from-ledger 10             # 从他已判的账本随机抽 10 篇（有标准答案）
  python judge_gateway.py --from-ledger 10 --hard      # 只抽改判过的硬骨头
输出：_系统数据/verdicts_gateway_<ts>.json
"""
import argparse
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.request

BASE = r"D:\Work\小红书点赞分析"
DATA = os.path.join(BASE, "_系统数据")
ANS = os.path.join(BASE, "b_answers")
GW3100 = "http://127.0.0.1:3100/v1/chat/completions"
GW8787 = "http://127.0.0.1:8787/v1/chat/completions"
MODEL = "fast"             # 二审默认线（gemini-3.5-flash-lite 实测最快最稳；free-high 批量下坏、free-flash 烧 longcat 额度）
PROVIDER = "buddy"        # 二审默认：Buddy2API 的 qoder qfmodel（2026-10-11 实测与他 10/10 一致）
BUDDY_MODEL = "qoder/qfmodel"   # 客户端代号，Buddy2API 侧解析为 qwen-flash（bailian-qwen3.5-flash）
CONCURRENCY = 3              # 免费线并发上限（5 实测触发限流，降 3）
STAGGER = 2.5                # 每篇启动间隔（秒）
MAX_TOKENS = 500             # 300 实测被截断出不完整 JSON
RETRY = 2                    # 每篇失败重试次数

def _api_key():
    if PROVIDER == "buddy":
        p = os.path.join(r"D:\项目\ai-hub\search_gateway\data", "channels.json")
        return json.load(open(p, encoding="utf-8"))["keys"]["buddy"]
    p = os.path.join(r"D:\项目\ai-hub\search_gateway\data", "api_state.json")
    return json.load(open(p, encoding="utf-8"))["api_key"]


def _endpoint():
    return GW8787 if PROVIDER == "buddy" else GW3100

SYSTEM = """你是小红书笔记筛选二审员。用户是郭老师：小学心理健康教育老师＋AI 开发者，
自己的系统＝Obsidian Work 知识库 / Vibe Coding 项目 / 小红书运营 / AI 内容创作 / 赚钱与产品思路。
判定轴：**连接“他自己系统”的留，纯外部世界的删。** 逐条对照判据后只输出 JSON。

【保留判据】（满足任一）
1 已落地实物/他明确要动手
2 不过时的认知/方法论（脱离工具版本）
3 可迁移技术思路（能用到 AI 创作/知识管理/小红书/Vibe Coding）
4 稀缺生活/社交程序知识（“怎么办”的隐性规则；保命/应急类算——来不及搜；公开显性政策不算）
5 顶级 AI 公司应用 AI 的方法论理念（公司级理念留；具体领域工作流如 Stata 删）
6 深度在地合集/攻略（长期经验沉淀的合集留；单点探店种草删）
7 心理/家庭关系专业内容；三观/人生选择/多元思想（留）
8 可改造基座型资产（“能基于他的东西修改”留；已有更强替代→删）
9 赚钱/变现方法（他要“多多学习赚钱方法，还能用 AI 去操作”——从宽留）
10 人物/信源（单篇可删但作者思路可学→保留“人”。**只对已登记人物生效**：
   艾丽的无废话财经。其他访谈对象不算——科研/行业人物访谈属删除判据 18）
11 未来计划场景的思路（“我以后会开店/做XX”留；“只有正好在做”删）

【他的身份加成】小学心理健康教育老师＋AI 开发者。能反向用于教学、心理课、
班级管理、课件/教具的方法论＝主线相关（例：考研背书法→他教学可借用→留）。
【时效分级】会过时但值得留的信息（平台评测/价格/政策）：短期 7 天／中期 1 个月／长期——
  保留但标注保质期，由任务 C 到期复核。**不要因为“会过时”直接删**（opus5.5 平台评测＝中期保留）。

【删除判据】（命中即删，多为多条同中）
1 会过时的情报（版本号/免费额度/优惠/抽奖/限免）
2 要花钱/订阅；重折腾环境（WSL/OAuth/命令行部署）；硬件不支持
3 纯软广/四无（无工具名无步骤无提示词无链接）
4 与主线无关且不属保留判据 4
5 高风险（封号/实盘炒币理财）
6 他已自行完成或落地链路太长
7 对他是降级方案（他能直接写代码）
8 已有更强替代
9 炫技无市场（技术漂亮但无应用场景，“只能炫技”）
10 场景性知识（“只有处在那个场景时才需要”）
11 需要时搜得到的操作性内容（“我需要时去搜就行，不用收藏”）
12 一时兴起的好看/惊艳
13 纯认知乐趣/跨界思维模型（无落地场景）
14 与主轴无关的通用科普（数学/食品/医学常识，知识正确但不进主线）
15 工具不可用（他用不了的，如 Codex）
16 音乐/乐器演奏类（他兴趣但不落地；音乐理论除外→留）
17 自嗨整活（“只能自己玩”，无产出路径）
18 科研/行业人物访谈（科研经历/成功叙事；三观访谈除外→留）
19 需真人指导/吃天赋的技能（自学易练错、靠天赋的身体技能）
20 AI 进步使其成一句话的事（纯能力展示，模型一代更迭即过时；能拿来当基座改的留）
21 英语学习/备考类（学科绑定的英语方法/备考资料；通用记忆方法论如背书法除外→留）

【输出】只输出一行 JSON：{"verdict":"keep|drop","reason":"一句话理由，引用判据编号"}"""

def _read_ids_from_ledger(n, hard_only):
    led = os.path.join(DATA, "text_review_verdicts.jsonl")
    items = []
    for ln in open(led, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        for it in r.get("items", []):
            if it.get("id") and it.get("你"):
                items.append(it)
    if hard_only:
        items = [it for it in items if it.get("一审") and it["一审"] != it["你"]]
    random.seed()
    random.shuffle(items)
    return [it["id"] for it in items[:n]]

def _judge_one(nid):
    for attempt in range(RETRY + 1):
        fp = os.path.join(ANS, nid + ".txt")
        if not os.path.exists(fp):
            return {"id": nid, "err": "no_fulltext"}
        note = open(fp, encoding="utf-8").read()[:5000]
        user = "笔记全文：\n%s\n\n按判据判定，只输出 JSON。" % note
        body = json.dumps({"model": MODEL,
                           "messages": [{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": user}],
                           "max_tokens": MAX_TOKENS, "temperature": 0.2}).encode("utf-8")
        req = urllib.request.Request(_endpoint(), data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + _api_key()})
        try:
            raw = urllib.request.urlopen(req, timeout=150).read().decode("utf-8", "ignore")
            resp = json.loads(raw)
            if "error" in resp:
                return {"id": nid, "err": "gateway_error: " + str(resp["error"])[:100]}
            content = resp["choices"][0]["message"].get("content") or ""
            m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', content)
            if not m:
                if attempt < RETRY:
                    time.sleep(3)
                    continue
                return {"id": nid, "err": "no_json", "raw": content[:150]}
            j = json.loads(m.group(0))
            v = j.get("verdict")
            if v not in ("keep", "drop"):
                if attempt < RETRY:
                    time.sleep(3)
                    continue
                return {"id": nid, "err": "bad_verdict:" + str(v)}
            return {"id": nid, "verdict": v, "reason": j.get("reason", "")}
        except Exception as e:
            if attempt < RETRY:
                time.sleep(4)
                continue
            return {"id": nid, "err": str(e)[:120]}
    return {"id": nid, "err": "retry_exhausted"}

def main():
    global MODEL, PROVIDER, MAX_TOKENS
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--from-ledger", type=int, default=0)
    ap.add_argument("--hard", action="store_true")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--provider", default="gateway", choices=["gateway", "buddy"])
    ap.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = ap.parse_args()
    MODEL = args.model
    MAX_TOKENS = args.max_tokens
    PROVIDER = args.provider
    if PROVIDER == "buddy" and args.model == "fast":
        MODEL = BUDDY_MODEL
    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    elif args.from_ledger:
        ids = _read_ids_from_ledger(args.from_ledger, args.hard)
    else:
        ap.error("需要 --ids 或 --from-ledger")
    print("二审（网关 %s）：%d 篇，并发 %d" % (MODEL, len(ids), args.concurrency))

    from concurrent.futures import ThreadPoolExecutor
    results, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {}
        for i, nid in enumerate(ids):
            time.sleep(STAGGER)
            futs[ex.submit(_judge_one, nid)] = nid
        for fu in futs:
            r = fu.result()
            results.append(r)
            tag = r.get("verdict") or ("ERR:" + str(r.get("err"))[:40])
            print("  %s → %s" % (r["id"][:8], tag))
    print("耗时 %.0fs" % (time.time() - t0))

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(DATA, "verdicts_gateway_%s.json" % ts)
    json.dump({"model": MODEL, "ts": ts, "results": results},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("输出:", out)

if __name__ == "__main__":
    main()
