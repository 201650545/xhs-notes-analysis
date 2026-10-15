import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
import json, subprocess, os

BASE = r"D:\workbuddy 工作空间"
LARK = r"C:\Users\<USER_NAME>\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\lark-cli.cmd"
BASE_TOKEN = get_cred("FEISHU_BASE_TOKEN", "<FEISHU_BASE_TOKEN>")
TABLE_ID = get_cred("FEISHU_TABLE_ID", "<FEISHU_TABLE_ID>")

with open(os.path.join(BASE, "_dd_results_20260903.json"), "r", encoding="utf-8") as f:
    results = json.load(f)

with open(os.path.join(BASE, "_liked_list_20260903_typed.json"), "r", encoding="utf-8") as f:
    typed = json.load(f)
type_map = {it["id"]: it["type"] for it in typed["items"]}

# 每条的精炼总结（与报告一致）
summaries = {
    43: "经典称重逻辑题：十堆巧克力外观相同，其中一堆有毒（正常10克/块、有毒11克/块），要求只用一次称重找出有毒堆。解法：从第1堆取1块、第2堆取2块…第10堆取10块共55块一起称，正常应550克，多出的克数即有毒堆编号。核心是用数字编码一次锁定目标。",
    44: "教师节专属福利汇总：夸克教育计划（教师认证领90天会员+扫描王VIP+网盘VIP）、支付宝「中国教师」小程序（认证领88元红包）、WPS教师认证领3个月AI会员、爱奇艺教师VIP 5折、腾讯WorkBuddy教师节积分兑换等。部分福利限量先到先得。",
    45: "大模型免费API选型对照表：免费额度最大选Agnes AI、NVIDIA NIM、Gemini Flash；中文能力最强选智谱GLM-4.7-Flash、硅基流动Qwen3-8B；推理速度最快选Groq、Cerebras；一个key打多模型选OpenRouter、Cloudflare Workers AI。提醒区分永久免费层与试用额度。",
    46: "阿里云「云工开物」学生专属300元优惠券，可用于调用DeepSeek、Kimi、GLM、Qwen等国内主流大模型API（DashScope平台，兼容模式接口）。有效期至2027年8月21日，适合学生党白嫖API额度。",
    47: "对话体寓言诗短视频：挑水人每天打水装满大桶却只分到一碗水，大桶主人以「我有大桶」独占剩余。挑水人不甘被剥削，自己琢磨发明生产工具，最终觉醒反抗。以「挑水」隐喻劳动与分配，结尾诗句点题，探讨劳动价值与公平。",
    48: "经典「毒酒测鼠」逻辑题：1000瓶酒1瓶有毒，10只老鼠喝到毒酒1小时发作，3小时内找出毒酒。核心是利用二进制编码与组合测试——n只老鼠可测2ⁿ-1瓶，10只可测1023瓶。老鼠倒地/不倒地对应二进制1/0，揭示计算机信息编码本质。",
    49: "第三方开源项目将ChatGPT Web直接接入OpenAI Codex，让ChatGPT作为Codex的底层推理模型——Codex保留任务调度、Shell、文件操作等「手脚」能力，把「大脑」换成ChatGPT Web。适合Codex额度不够但订阅ChatGPT Plus/Pro的用户变相续命。",
    50: "将已停更的考公博主「网友红领巾」（考公界三大真神之一）的历史经验帖和视频喂给AI，通过蒸馏技术复刻其思考技能。验证发现AI解答言语理解题的思路与原作高度相似，实现「赛博重生」随时答疑。",
    51: "30岁全职羊毛人第一视角沉浸式拆箱：通过各大平台薅羊毛活动抢到海量0.01元/几毛钱日用品——一分抢购（得力收纳盒、老干妈、大米10来斤、高露洁牙膏10来支、洁厕灵10来瓶、打印纸3000张、可乐美年达18提等）、几毛钱（洗手液10瓶、牙刷10来支等）、一块钱（黄天鹅鸡蛋4单）。",
    52: "免费白嫖大模型资源推广：平台含DeepSeek V4 Pro、Qwen3.8 Max等29个大模型，每天500万Token免费额度，20+免费模型+限量AI生图+148种AI语音TTS。只需注册无需绑卡，永久免费Free套餐，另有按月/季/年付费进阶套餐。",
}

tags = {
    43: "#逻辑思维 #数学谜题 #科普 #趣味数学",
    44: "#教师节 #福利 #薅羊毛 #会员",
    45: "#大模型 #API #免费资源 #开发者",
    46: "#阿里云 #DeepSeek #API #学生福利",
    47: "#寓言 #劳动价值 #诗歌 #社会思考",
    48: "#逻辑推理 #二进制 #计算机 #科普",
    49: "#ChatGPT #Codex #AI编程 #开源",
    50: "#考公 #AI蒸馏 #赛博重生 #知识传承",
    51: "#薅羊毛 #沉浸式拆箱 #省钱 #囤货",
    52: "#免费大模型 #AI工具 #薅羊毛 #资源分享",
}

fields = ["标题", "序号", "作者", "点赞数", "链接", "内容类型", "分类", "点点总结", "主题标签", "存档文件"]
rows = []
for r in sorted(results, key=lambda x: x["seq"]):
    seq = r["seq"]
    rows.append([
        r["title"],
        seq,
        r["author"],
        r["like"],
        r["href"],
        type_map.get(r["id"], "视频"),
        "小红书点赞分析",
        summaries.get(seq, ""),
        tags.get(seq, ""),
        os.path.basename(r["raw_file"]),
    ])

payload = {"fields": fields, "rows": rows}
payload_json = json.dumps(payload, ensure_ascii=False)

payload_file = os.path.join(BASE, "_lark_payload_20260903.json")
with open(payload_file, "w", encoding="utf-8") as f:
    f.write(payload_json)

cmd = [LARK, "base", "+record-batch-create",
       "--base-token", BASE_TOKEN,
       "--table-id", TABLE_ID,
       "--json", "@./_lark_payload_20260903.json",
       "--as", "user", "--format", "json"]

print("rows:", len(rows))
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=BASE)
print("STDOUT:", result.stdout[:2000])
print("STDERR:", result.stderr[:1000])
print("RC:", result.returncode)
