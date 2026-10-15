# -*- coding: utf-8 -*-
"""全量批处理 v3：CDP卡片 + 分类深度提示词（含提示词摘录条款 + 笔记/联网分区）。
跑 30 条，断点续传（仅跳过带 v3 标记的成品）。"""
import json
import os
import subprocess
import time
import urllib.request

API = "http://127.0.0.1:10086/command"
SESSION = "xhs"
HOME = "https://www.xiaohongshu.com/explore"
ITEMS = r"D:\Work\小红书点赞分析\_liked_list_now.json"
OUT_DIR = r"D:/workbuddy 工作空间/点点分析结果/raw_20260923/final"
VERSION = "v3-分区版"

# ---------- 公共分区约束 ----------
ZONE = "补充规则：笔记信息不足时可以联网搜索公开资料补充，但必须分区标注——先写【笔记内容】（仅限笔记真实出现的信息），再写【联网补充】（搜索所得须注明来源，如GitHub README、官网、媒体报道）。所有链接、GitHub地址、数据都必须标明来自笔记还是联网，禁止混为一谈、禁止把搜到的内容说成笔记里的。\n\n"

# ---------- 分类 ----------
CAT_A, CAT_B, CAT_C, CAT_D = "A技术", "B变现", "C方法论", "D生活"
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


# ---------- 不分析的内容（用户指定：做菜类、影视解说不分析，直接取消点赞）----------
EXCLUDE_IDS = {"6aa6273300000000260080a7"}  # #17 炒牛肉多少秒才好吃
KW_EXCLUDE = ["炒牛肉", "炒肉", "做菜", "做饭", "食谱", "菜谱", "家常菜",
              "红烧", "清蒸", "烘焙", "怎么做好吃", "多少秒才好吃",
              # 影视解说类（2026-09-24 用户指定：不分析，直接取消点赞）
              "影视解说", "电影解说", "电视剧解说", "剧集解说", "剧情解说", "好剧解说",
              "影视剪辑", "影视混剪", "影视盘点", "一口气看完", "一剪到底"]


def excluded(note_id, title):
    return note_id in EXCLUDE_IDS or any(k in title for k in KW_EXCLUDE)


# ---------- 四类提示词 ----------
P_A = """请认真观看这条笔记的视频画面、口播、字幕、配图和正文，做一次可复现级的深度拆解。只依据笔记真实内容作答，没提到的写"笔记未提及"，严禁编造，工具名和链接原样照抄。
""" + ZONE + """一、素材与想法
1.用什么素材（数据/内容源/账号/API/平台信息）？从哪来、怎么拿到？2.核心想法：看到什么痛点或机会、想到什么点子、要达成什么效果，完整描述来龙去脉。3.新在哪、省在哪、强在哪？

二、实现方式与技术原理
1.从0到成品分哪几步，按顺序说明；2.背后依赖什么机制（插件/hook/RAG/Agent编排/API/定时任务/工作流），讲清原理；3.最有技术含量的是哪一步，怎么运转。

三、AI与工具清单
逐个列出每个模型、产品、工具、框架、插件：准确名称（含版本号）、负责什么、免费还是付费。

四、项目来源与链接
1.提到GitHub或代码仓库就原样给完整地址、用途、作者，没有写"未提供GitHub地址"；2.其他链接、公众号、群、文档、官网、网盘全部列出；3.是否基于开源项目二次创作，原项目叫什么。

五、视频中出现的提示词/指令（重点）
如果视频演示了他实际输入给AI的提示词或指令（画面、字幕、口播中能看到），逐条逐字原样摘录，注明每条用在哪个环节、输入给哪个工具；没有就写"视频中未出现提示词"，不要编造。

六、复现指南
1.前置条件（账号/环境/基础/成本）；2.最简行动清单；3.难点与坑（封号/收费/失效/门槛）。

七、一两句话总结最该记住的关键点。"""

P_B = """请认真观看这条笔记的视频画面、口播、字幕、配图和正文（评论区补充也要看），做一次可照抄级的深度拆解。只依据笔记真实内容，没提到的写"笔记未提及"，工具名、金额、链接原样照抄。
""" + ZONE + """一、项目定位
做了什么AI内容项目（AI视频/漫剧/美剧/切片）？成品什么样、发在哪个平台？

二、素材与想法
1.题材、风格、受众？剧本、人物形象、配音、画面素材分别从哪来，原创还是改编；2.核心创意和差异化是什么，为什么选这个题材。

三、制作流程
1.从选题到发布分几步，每步用什么、怎么做，按顺序写清；2.画面怎么生成、人物怎么保持一致、口型配音怎么对、怎么剪辑合成；3.一条/一集实际制作周期。

四、AI与工具清单
逐个写明准确名称（含版本/型号）、负责环节（剧本/出图/视频/配音/剪辑）、免费还是付费、花费多少。

五、成本与收益（数字原样照抄）
1.投入：逐项列会员费、生成费，共多少钱、多少时间、几个人；2.产出：条数、播放量、点赞、涨粉、各项收入；3.赚还是亏，变现路径怎么拿钱（平台激励/中视频/带货/接单）。

六、视频中出现的提示词（重点）
如果演示了实际使用的生图、生视频、剧本、配音等提示词，逐条逐字原样摘录，注明用途和输入工具；没有写"视频中未出现提示词"。

七、链接与复现
GitHub/模板/教程/工作流/提示词合集地址原样列出，没有写"未提供"；新手最简步骤、启动成本、风险坑。

八、一句话总结最该记住的点。"""

P_C = """请认真观看这条笔记的口播、字幕、正文和评论区补充，做一次可执行级的深度拆解。只依据笔记真实内容，没提到的写"笔记未提及"，人名、金额、数据原样照抄。
""" + ZONE + """一、谁在讲、讲什么
创作者身份、经历、成绩（用他给的数据说话）；针对什么人群、解决什么困惑。

二、核心观点
1.最想传达的主张；2.完整论证逻辑链；3.有哪些反常识观点。

三、具体怎么做
1.完整路径分几步，每步具体动作；2.各环节判断标准和选择依据；3.他强调"不要做什么"。

四、案例与数据（原样照抄）
1.他自己案例的关键数字（收入、时间、投入、结果）；2.引用的别人案例；3.提到的平台、渠道、工具、书籍、账号。

五、可落地建议
1.零起点今天就能做的第一个动作；2.前中后三期分别聚焦什么；3.风险、代价、避坑提醒。

六、视频中出现的提示词/话术（重点）
如果视频展示了他实际使用的提示词、文案模板、私信话术、操作指令等，逐条逐字原样摘录并注明用途；没有写"视频中未出现"。

七、金句摘录
摘录3~5句最有冲击力的原话。"""

P_D = """请认真观看这条笔记的视频画面、口播、字幕、配图和正文，把有价值的信息完整细致地整理出来。只依据笔记真实内容，没提到的写"笔记未提及"，数字、名称、步骤、配方一字不差。
""" + ZONE + """一、内容定位
什么领域（音乐/美食/健康/语言/生活技能等）？作者身份？想教会观众什么？

二、内容详细讲解（重点）
1.按内容自身顺序从头到尾完整复述，不漏关键细节；2.方法、步骤、配方、参数、时间、数字、术语全部原样列出；3.演示类内容分步写清每步怎么做。

三、核心知识点
1.关键结论；2.容易搞错、需特别注意的要点；3.作者的个人经验和小贴士。

四、视频中出现的提示词/操作文字（重点）
如果演示中出现他输入给AI的提示词、搜索词、软件指令、配方文本等可照抄的文字，逐条逐字原样摘录并注明用途；没有写"视频中未出现"。

五、实用信息清单
可直接拿来用的清单、表格、口诀、链接、工具名、材料清单等。

六、一句话总结最值得收藏的点。"""

PROMPTS = {CAT_A: P_A, CAT_B: P_B, CAT_C: P_C, CAT_D: P_D}

# ---------- 行动路由（深度分析后的第二次短提问；受搜索框长度限制，须短）----------
ROUTE_PROMPT = """只依据这条笔记的真实内容，判断"我"该怎么处理它。不要复述笔记、不要解释、不要加序号，严格逐行照下面格式输出（每行必须有）：
路由：复刻闭环 或 学习闭环 或 归档观察（三选一：能近期做出具体产出选复刻；有长期认知价值选学习；价值低选归档）
处理意图：复刻 或 学习 或 灵感 或 跟踪 或 仅了解（五选一）
优先级：P0 尽快 或 P1 本周 或 P2 以后 或 P3 资料（四选一）
时效：这条信息多久内有效（如"7天""长期"）
行动成本：低 或 中 或 高，并给大致耗时
最小下一步：一个具体动作，动词开头，30分钟内能开始
复刻目标：走复刻闭环要验证什么结论；否则写"不适用"
核心知识：值得长期记住的1~2点，每点一句话；没有写"无"
路由理由：一句话说明为什么这么路由"""
REFUSE = ["无法直接访问", "无法访问小红书", "暂时无法为您总结", "我目前无法", "请提供具体"]


# ---------- 浏览器操作 ----------
def cmd(action, args=None, timeout=120):
    body = json.dumps({"action": action, "args": args or {}, "session": SESSION}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    if not r.get("ok"):
        raise RuntimeError(json.dumps(r, ensure_ascii=False)[:200])
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
        if json.loads(ev(STATE_JS))["hasCard"]:
            return True
    return False


def press_enter():
    ev(r"""
(() => {
  const ta = document.querySelector('#search-input-in-feeds');
  ta.focus();
  const o = {key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true,composed:true};
  ['keydown','keypress','keyup'].forEach(t => ta.dispatchEvent(new KeyboardEvent(t,o)));
  return 'sent';
})()
""")


def wait_answer(timeout_s=240):
    last, stable = "", 0
    for i in range(timeout_s // 3):
        time.sleep(3)
        d = json.loads(ev(r"""
(() => {
  const ai = [...document.querySelectorAll('.ai-message')].filter(e => e.offsetParent);
  if (!ai.length) return JSON.stringify({state:'waiting', len:0, text:''});
  const x = ai[ai.length-1];
  return JSON.stringify({state: x.className.indexOf('finished')>-1?'done':'streaming',
                         len: x.innerText.trim().length, text: x.innerText.trim()});
})()
"""))
        if d["state"] == "done":
            stable = stable + 1 if d["len"] == len(last) and d["len"] > 100 else 0
        last = d["text"]
        if stable >= 2 and d["len"] > 100:
            return last
    return last


def quality(t):
    return len(t) > 400 and not any(k in t for k in REFUSE)


def run_one(href, prompt):
    cmd("navigate", {"url": HOME, "newTab": False})
    time.sleep(6.5)
    # 进入问点点模式 + 发送，最多重试3轮（处理面板未展开/未跳转）
    for _ in range(3):
        cmd("click", {"selector": "button.wendian-btn"})
        time.sleep(3)
        if not paste_link_as_card(href):
            time.sleep(2)
            continue
        time.sleep(1)
        cmd("fill", {"selector": "#search-input-in-feeds", "value": prompt})
        time.sleep(1.5)
        press_enter()
        time.sleep(6)
        if "ai_chat_tab" in ev("location.href"):
            return wait_answer()
        time.sleep(2)
    return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = json.load(open(ITEMS, encoding="utf-8"))["items"]
    print(">>> v3 全量 %d 条，输出 %s" % (len(items), OUT_DIR), flush=True)
    ok = skip = fail = excluded_n = 0
    fails = []
    for i, it in enumerate(items):
        if excluded(it["id"], it["title"]):
            excluded_n += 1
            print("[%2d] ⊘ 跳过(做菜/影视解说) %s" % (i, it["title"][:30]), flush=True)
            continue
        cat = classify(it["title"])
        path = os.path.join(OUT_DIR, "final_%02d_%s.txt" % (i, it["id"]))
        if os.path.exists(path):
            head = open(path, encoding="utf-8").read(200)
            if VERSION in head and len(open(path, encoding="utf-8").read()) > 500:
                skip += 1
                print("[%2d] 跳过 %s" % (i, cat), flush=True)
                continue

        prompt = PROMPTS[cat]
        print("[%2d/%d] [%s|%d字] %s" % (i, len(items) - 1, cat, len(prompt), it["title"][:32]), flush=True)
        text = None
        for attempt in (1, 2):
            try:
                text = run_one(it["href"], prompt)
            except Exception as e:
                print("     异常: %s" % str(e)[:80], flush=True)
                text = None
            if text and quality(text):
                break
            print("     重试(%s)" % ("空/拒答" if not text else len(text)), flush=True)
            time.sleep(3)

        if text and quality(text):
            with open(path, "w", encoding="utf-8") as f:
                f.write("【模板版本】%s\n【类型】%s\n【序号】%d\n【标题】%s\n【作者】%s\n【点赞】%s\n【链接】%s\n\n【点点回复】\n%s\n"
                        % (VERSION, cat, i, it["title"], it.get("author", ""),
                           it.get("like", ""), it["href"], text))
            ok += 1
            print("     ✅ %d字" % len(text), flush=True)
        else:
            fail += 1
            fails.append((i, cat, it["title"][:24]))
            print("     ❌ 失败" % (), flush=True)
        time.sleep(2)

    print("\n>>> 完成：成功 %d | 跳过(已有) %d | 不分析(做菜/影视解说) %d | 失败 %d"
          % (ok, skip, excluded_n, fail), flush=True)
    for f in fails:
        print("   失败:", f, flush=True)


if __name__ == "__main__":
    main()