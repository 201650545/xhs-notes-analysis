# -*- coding: utf-8 -*-
"""第二轮：按内容类型定制提问，深挖素材/想法、实现原理、AI工具、GitHub来源。"""
import json
import os
import sys
import time
import urllib.request

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
HOME = "https://www.xiaohongshu.com/explore"
ITEMS = r"<PROJECT_DIR>\_liked_list_now.json"
OUT_DIR = r"D:/workbuddy 工作空间/点点分析结果/raw2_20260923"

REFUSE = ["无法直接访问", "无法访问小红书", "暂时无法为您总结", "我目前无法", "请提供具体", "可以尝试以下方法"]

# ---------- 分类 ----------
CAT_A = "AI工具技术"
CAT_B = "AI内容变现"
CAT_C = "自媒体赚钱"
CAT_D = "生活知识"

KW_B = ["AI美剧", "AI漫剧", "AI视频", "切片", "自制AI"]
KW_A = ["Jev", "Cline", "Kimi", "K3", "开源", "vibecoding", "智能体", "skill", "白板",
        "语音控制", "AI红利", "talents", "自学入门", "文本精读"]
KW_C = ["赚钱", "生意", "事业", "第一桶金", "自媒体", "赛道", "变现", "万玩家", "英语"]


def classify(title):
    if any(k in title for k in KW_B):
        return CAT_B
    if any(k in title for k in KW_A):
        return CAT_A
    if any(k in title for k in KW_C):
        return CAT_C
    return CAT_D


# ---------- 分类提示词（深度版 v2）----------
P_A = """你是一位资深 AI 技术拆解分析师。我给你一个小红书笔记/视频链接，请你认真观看、阅读其中的全部内容（视频画面、口播、字幕、配图、正文、评论区补充都要看到），然后做一次"可复现级"的深度拆解。

要求：
- 只基于笔记里真实出现的信息作答，严禁脑补、严禁编造链接或项目名；
- 凡是笔记里没有提到的信息，明确写"笔记未提及"，不要含糊带过；
- 出现的工具名、模型名、网站名、代码库地址，必须原样照抄，一个字符都不能错；
- 按下面的结构逐条回答，每条都要展开写充分，不要只给一句话。

一、这是什么（一句话定位）
用一句话说清这个笔记讲的是一个什么东西/项目/玩法，它解决谁的什么问题。

二、素材与想法（重点，写详细）
1. 原始素材：创作者用的是什么素材？（例如：什么数据、什么内容源、什么账号、什么音视频、什么 API、什么平台上的信息）素材从哪里来、怎么拿到的？
2. 核心想法/创意：他的核心想法到底是什么？请把这个想法的来龙去脉完整描述清楚——他看到了什么机会或痛点，想到了一个什么点子，打算用这个点子达成什么效果。
3. 想法的巧妙之处：这个想法为什么值得点赞？和普通做法相比，新在哪、省在哪、强在哪？

三、实现方式与技术原理（重点，分步骤）
1. 完整实现流程：从 0 到成品一共分哪几步？请按顺序列出每一步具体做什么。
2. 技术原理：背后依赖什么技术机制？（例如：浏览器插件读取页面、微信 hook、RAG 检索、Agent 编排、API 调用、定时任务、自动化工作流等）请把原理讲明白。
3. 关键环节拆解：整个流程中最核心、最有技术含量的环节是哪一步？它具体怎么运转的？

四、用到的 AI 与工具清单（逐个列出）
请把笔记中出现的每一个 AI 模型、AI 产品、编程工具、框架、插件、平台都列出来，并逐个写明：
- 准确名称（有版本号、型号名一并写出，例如 Kimi K2/K3、Claude Sonnet 4、Cline、Jev 等）；
- 它在流程里负责干什么；
- 是免费还是付费、大概价格（笔记提到才写）。

五、项目来源与链接（重点，必须逐条核对）
1. 笔记中是否提到 GitHub 开源项目、代码仓库或可下载地址？
   - 如果提到：原样给出完整 GitHub 地址（https://github.com/……），并说明这个仓库是做什么的、作者是谁；
   - 如果没提到：明确写"未提供 GitHub 地址"，不要编造。
2. 除 GitHub 外，笔记里还出现了哪些可点击的链接、公众号、群、文档、官网、飞书/网盘地址？请全部原样列出。
3. 如果内容是基于某个已有开源项目二次创作的，请指出原项目名称。

六、复现指南（如果我想自己做一个）
1. 前置条件：需要什么账号、什么环境、什么基础、大概多少成本；
2. 复现步骤：照着做的最简行动清单；
3. 难点与坑：笔记作者提到或能看出的坑、限制、风险（封号、收费、失效、技术门槛等）。

七、值得我收藏的一句话
用一两句话总结：我以后想用的时候，最该记住的关键点是什么。

笔记链接：%s"""

P_B = """你是一位资深 AI 内容创业拆解分析师。我给你一个小红书笔记/视频链接，内容是关于用 AI 做内容（AI 视频/AI 漫剧/AI 美剧/切片号等）并尝试变现的。请你认真观看全部内容（视频画面、口播、字幕、配图、正文、评论区都要看到），做一次"可照抄级"的深度拆解。

要求：
- 只基于笔记里真实出现的信息作答，严禁脑补；没提到的写"笔记未提及"；
- 工具名、平台名、金额、链接原样照抄；
- 按下面结构逐条展开，写充分。

一、这是什么（一句话定位）
创作者做了一个什么 AI 内容项目？最终成品长什么样、发在哪个平台？

二、创作素材与想法（重点，写详细）
1. 题材与内容：做的是什么故事/主题？什么风格（写实、动漫、影视感）？面向什么受众？
2. 素材来源：剧本、人物形象、配音、画面素材分别从哪来？是原创还是改编？
3. 核心想法：他为什么选这个题材/这种做法？核心创意和差异化是什么？

三、制作流程与实现方式（重点，分步骤）
1. 完整制作流水线：从选题到发布一共几步？每一步用什么做、怎么做，按顺序写清；
2. 关键技术环节：画面怎么生成、人物怎么保持一致性、口型/配音怎么对、视频怎么剪辑合成；
3. 一条/一集内容的实际制作周期。

四、用到的 AI 与工具清单（逐个列出）
每个工具写明：准确名称（含版本/型号）、负责哪个环节、免费还是付费、大概花费。
（例如：剧本用什么模型、出图用什么、视频生成用什么、配音用什么、剪辑用什么）

五、成本与收益账本（重点，数字原样照抄）
1. 投入：总共花了多少钱（逐项列出：会员费、生成费等）、多少时间、几个人；
2. 产出：发了几条/几集、播放量、点赞、涨粉、红包/分成/广告等各项收入；
3. 算账：到底赚了还是亏了？单位成本和单位收益是多少？
4. 变现路径：钱具体是怎么拿到的（平台激励、中视频计划、带货、接单等）。

六、项目来源与链接
1. 是否提供 GitHub、模板、教程、工作流文件、提示词合集？有就原样给完整地址，没有写"未提供"；
2. 笔记里出现的其他链接、账号、群、文档全部列出。

七、复现指南
1. 新手照做的最简步骤；
2. 前置条件与启动成本；
3. 难点、坑和风险（限流、版权、账号权重、成本失控等）。

八、值得收藏的一句话

笔记链接：%s"""

P_C = """你是一位商业与自媒体方法论分析师。我给你一个小红书笔记/视频链接，内容是关于赚钱、事业、自媒体、个人成长的经验分享。请你认真观看全部内容（口播、字幕、正文、评论区补充都要看到），做一次"可执行级"的深度拆解。

要求：
- 只基于笔记真实内容，严禁脑补；没提到的写"笔记未提及"；
- 人名、平台名、金额、时间、数据原样照抄；
- 按下面结构逐条展开。

一、这是谁、在讲什么（背景定位）
创作者本人的身份、经历、成绩（用他自己给出的数据说话）；这条内容针对什么人群、解决什么困惑。

二、核心观点（写详细）
1. 他最想传达的核心主张是什么？
2. 支撑这个主张的完整逻辑链条：他是怎么一步步论证的？
3. 有哪些反常识/刷新认知的观点？

三、具体怎么做（方法论分步骤）
1. 他建议的完整路径/方法分几步？每一步具体动作是什么；
2. 每个环节的判断标准、选择依据是什么；
3. 他特别强调"不要做什么"？

四、案例与数据（逐条列出，原样照抄）
1. 他自己的案例：关键数字（收入、时间、投入、结果）；
2. 他引用的别人的案例；
3. 提到的平台、渠道、工具、书籍、账号名称。

五、可落地建议
1. 如果我是零起点，今天就能开始做的第一个动作是什么；
2. 按他的方法，前期/中期/后期分别该聚焦什么；
3. 风险、代价和他给出的避坑提醒。

六、金句摘录
摘录笔记里最有冲击力、最值得记住的 3~5 句原话。

笔记链接：%s"""

P_D = """你是一位知识内容整理分析师。我给你一个小红书笔记/视频链接，请你认真观看全部内容（视频画面、口播、字幕、配图、正文都要看到），把其中有价值的信息完整、细致地整理出来。

要求：
- 只基于笔记真实内容，严禁脑补；没提到的写"笔记未提及"；
- 按下面结构逐条展开，信息尽量具体、保留原始细节（数字、名称、步骤、配方等一字不差）。

一、内容定位
这是什么领域的内容（音乐/美食/健康/语言学习/生活技能等）？作者是谁、什么身份？这条内容想教给观众/读者什么？

二、内容详细讲解（重点）
1. 从头到尾完整讲了什么？请按内容自身的顺序详细复述，不要漏掉关键细节；
2. 涉及的具体方法/步骤/配方/参数/时间/数字/术语，全部原样列出；
3. 如果是演示类内容（做饭、弹奏、操作等），分步骤写清每一步怎么做。

三、核心知识点
1. 关键结论有哪些；
2. 有哪些容易搞错、需要特别注意的要点；
3. 作者给出的个人经验、小贴士、补充说明。

四、实用信息清单
可以直接拿来用的信息：清单、表格、口诀、链接、工具名、材料清单等。

五、值得收藏的一句话

笔记链接：%s"""

PROMPTS = {CAT_A: P_A, CAT_B: P_B, CAT_C: P_C, CAT_D: P_D}


def cmd(action, args=None, timeout=90):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError("%s -> %s" % (action, json.dumps(r, ensure_ascii=False)[:200]))
    return r.get("data", {})


def ev(code):
    return cmd("evaluate", {"code": code})["value"]


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
  if (!ai.length) return JSON.stringify({state:'waiting'});
  const last = ai[ai.length - 1];
  return JSON.stringify({
    state: last.className.indexOf('finished') > -1 ? 'done' : 'streaming',
    text: last.innerText.trim()
  });
})()
"""

MODE_JS = "(() => { const ta = document.querySelector('#search-input-in-feeds'); return ta ? (ta.getAttribute('placeholder')||'') : 'none'; })()"


def quality(t):
    return len(t) > 400 and not any(k in t for k in REFUSE)


URL_JS = "location.href"


def run_one(href, prompt):
    cmd("navigate", {"url": HOME, "newTab": False})
    time.sleep(6.5)

    # 点击「问点点」→ 填写 → 回车；若发送后未跳转 ai_chat_tab，则重点一次重发
    sent_ok = False
    for round_i in (1, 2, 3):
        cmd("click", {"selector": "button.wendian-btn"})
        time.sleep(2.5)
        cmd("fill", {"selector": "#search-input-in-feeds", "value": prompt})
        time.sleep(0.8)
        ev(ENTER_JS)
        time.sleep(3.5)
        if "ai_chat_tab" in ev(URL_JS):
            sent_ok = True
            break
        time.sleep(1.5)
    if not sent_ok:
        return None, "回车后未跳转ai_chat_tab"

    for _ in range(30):
        time.sleep(3)
        try:
            d = json.loads(ev(READ_JS))
        except Exception:
            continue
        if d.get("state") == "done" and d.get("text"):
            return d["text"], "ok"
    return None, "超时"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = json.load(open(ITEMS, encoding="utf-8"))["items"]
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else len(items)

    print(">>> 第二轮 %d 条（%d~%d）" % (end - start, start, end - 1), flush=True)
    ok = skip = fail = 0

    for i in range(start, end):
        it = items[i]
        cat = classify(it["title"])
        path = os.path.join(OUT_DIR, "raw2_%d_%s.txt" % (i, it["id"]))
        if os.path.exists(path) and quality(open(path, encoding="utf-8").read()):
            skip += 1
            print("[%2d] 跳过 %s" % (i, cat), flush=True)
            continue

        print("[%2d/%d] [%s] %s" % (i, end - 1, cat, it["title"][:34]), flush=True)
        text, st = None, ""
        for attempt in (1, 2):
            try:
                text, st = run_one(it["href"], PROMPTS[cat] % it["href"])
            except Exception as e:
                text, st = None, "异常:%s" % str(e)[:70]
            if text and quality(text):
                break
            if attempt == 1:
                print("     重试(%s)" % st, flush=True)
                time.sleep(3)

        if text and quality(text):
            with open(path, "w", encoding="utf-8") as f:
                f.write("【类型】%s\n【标题】%s\n【作者】%s\n【链接】%s\n【点赞】%s\n\n【点点回复】\n%s\n"
                        % (cat, it["title"], it["author"], it["href"], it["like"], text))
            ok += 1
            print("     ✅ %d 字" % len(text), flush=True)
        else:
            fail += 1
            print("     ❌ %s" % st, flush=True)

    print("\n>>> 完成：成功 %d | 跳过 %d | 失败 %d" % (ok, skip, fail), flush=True)
    print(">>> 输出:", OUT_DIR, flush=True)


if __name__ == "__main__":
    main()