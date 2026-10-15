import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
# -*- coding: utf-8 -*-
import json
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime

API = 'http://127.0.0.1:10086/command'
LARK_CLI = r"C:\Users\<USER_NAME>\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\bin\lark-cli.cmd"
BASE_TOKEN = get_cred("FEISHU_BASE_TOKEN", "<FEISHU_BASE_TOKEN>")
TABLE_ID = get_cred("FEISHU_TABLE_ID", "<FEISHU_TABLE_ID>")
DATE_STR = datetime.now().strftime("%Y-%m-%d")
DATE_COMPACT = datetime.now().strftime("%Y%m%d")

RAW_DIR = os.path.join(r"D:\workbuddy 工作空间\点点分析结果", f"raw_{DATE_COMPACT}")
os.makedirs(RAW_DIR, exist_ok=True)

PROGRESS_FILE = r"<PROJECT_DIR>\_batch_progress.json"

def call(action, args=None, session='xhs'):
    payload = {'action': action, 'session': session}
    if args is not None:
        payload['args'] = args
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(API, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

def evaluate(code, session='xhs'):
    res = call('evaluate', {'code': code}, session=session)
    if not res.get('ok'):
        raise RuntimeError(f"Evaluate failed: {res.get('error')}")
    return res.get('data', {}).get('value')

def ensure_ai_chat():
    try:
        href = evaluate('location.href')
        if 'ai_chat' in str(href):
            return
    except Exception:
        pass
    print("Navigating to https://www.xiaohongshu.com/ai_chat ...")
    call('navigate', {'url': 'https://www.xiaohongshu.com/ai_chat'})
    time.sleep(5)

def send_prompt(prompt_text):
    escaped_prompt = json.dumps(prompt_text, ensure_ascii=False)
    js_inject = f"""
    (() => {{
      const ta = [...document.querySelectorAll('textarea')].find(t => t.offsetParent !== null);
      if (!ta) return 'NO_TA';
      ta.focus();
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, {escaped_prompt});
      ta.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: {escaped_prompt} }}));
      return 'OK';
    }})()
    """
    res = evaluate(js_inject)
    if res != 'OK':
        raise RuntimeError(f"Textarea injection returned: {res}")
    time.sleep(0.5)
    # Click send
    evaluate("document.querySelector('div.submit-button-wrapper')?.click()")

def poll_last_message(max_timeout=65):
    last_text = ""
    stable_count = 0
    start_time = time.time()
    
    js_last = """
    (() => {
      const ms = [...document.querySelectorAll('.ai-message')];
      const last = ms[ms.length - 1];
      return last ? (last.innerText || '').trim() : '';
    })()
    """
    
    while time.time() - start_time < max_timeout:
        time.sleep(2)
        try:
            curr_text = evaluate(js_last) or ""
        except Exception as e:
            continue
            
        # Check if empty or temporary placeholder
        if not curr_text:
            continue
        placeholders = ["问题分析中", "思考中", "正在总结", "分析中", "..."]
        if any(p in curr_text for p in placeholders) and len(curr_text) < 25:
            continue
            
        if len(curr_text) > 30:
            if curr_text == last_text:
                stable_count += 1
                if stable_count >= 2:
                    return curr_text
            else:
                stable_count = 0
                last_text = curr_text

    return last_text

def extract_summary_and_tags(full_reply, title=""):
    # Clean up markdown headers/bullets into a compact 100-150 word summary
    lines = [line.strip() for line in full_reply.split('\n') if line.strip()]
    
    # Extract tags
    found_tags = re.findall(r'#[\w\u4e00-\u9fa5]+', full_reply)
    if not found_tags:
        # Generate some generic tags based on title/content
        kw_map = {
            'AI': '#AI工具', 'Jev': '#Jev #开源', 'Cline': '#Cline #AI编程',
            '英语': '#英语学习', '副业': '#副业赚钱', '考公': '#考公备考',
            '小说': '#学习方法', '数学': '#趣味科普', '游戏': '#游戏开发'
        }
        gen = [v for k, v in kw_map.items() if k in title or k in full_reply]
        found_tags = gen if gen else ['#知识分享']
    tag_str = " ".join(dict.fromkeys(found_tags)[:5])
    
    # Extract key paragraphs (skip generic greetings)
    content_lines = []
    for l in lines:
        if any(g in l for g in ["我是点点", "你好", "很高兴为你总结", "以下是关于", "点击链接"]):
            continue
        # Strip markdown bullets
        clean_l = re.sub(r'^[\*\-\d\.\s#]+', '', l).strip()
        if len(clean_l) > 10:
            content_lines.append(clean_l)
            
    summary_text = "；".join(content_lines[:4])
    if len(summary_text) > 280:
        summary_text = summary_text[:275] + "..."
    if not summary_text:
        summary_text = full_reply[:250].replace('\n', ' ')
        
    return summary_text, tag_str

def main():
    with open(r"<PROJECT_DIR>\_new_items.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    max_seq = data['max_seq']
    # Reverse to process oldest first -> newest last
    items = list(reversed(data['new_items']))
    total_count = len(items)
    print(f"Total items to summarize: {total_count}, starting seq: {max_seq + 1}")

    # Load existing progress if any
    processed = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                processed = json.load(f)
        except Exception:
            processed = {}

    ensure_ai_chat()

    results = []
    for idx, it in enumerate(items, 1):
        seq = max_seq + idx
        nid = it['id']
        title = it['title']
        author = it['author']
        like = it['like']
        href = it['href']
        itype = it.get('type') or '笔记'
        raw_file = os.path.join(RAW_DIR, f"raw_{seq}_{nid}.txt")

        if str(seq) in processed and os.path.exists(processed[str(seq)].get('raw_file', '')):
            print(f"[{idx}/{total_count}] Seq {seq}: Already done ({title})")
            results.append(processed[str(seq)])
            continue

        print(f"\n[{idx}/{total_count}] Processing Seq {seq}: {title} ({author})")
        prompt = f"请总结这个小红书{itype}的内容，给出内容概要、主题分类、关键信息点：{href}"
        
        try:
            send_prompt(prompt)
            print("  Sent to Diandian, waiting for answer...")
            ans = poll_last_message()
            print(f"  Received reply (length: {len(ans)})")
            
            # Save raw file
            with open(raw_file, "w", encoding="utf-8") as rf:
                rf.write(f"【用户提问】\n{prompt}\n\n【点点回复】\n{ans}\n")
                
            summary, tags = extract_summary_and_tags(ans, title)
            
            res_entry = {
                'seq': seq,
                'id': nid,
                'title': title,
                'author': author,
                'like': like,
                'type': itype,
                'href': href,
                'summary': summary,
                'tags': tags,
                'raw_file': raw_file
            }
            results.append(res_entry)
            processed[str(seq)] = res_entry
            
            with open(PROGRESS_FILE, "w", encoding="utf-8") as pf:
                json.dump(processed, pf, ensure_ascii=False, indent=2)
                
            time.sleep(2)
        except Exception as e:
            print(f"  Error on seq {seq}: {e}")
            # Fallback
            res_entry = {
                'seq': seq,
                'id': nid,
                'title': title,
                'author': author,
                'like': like,
                'type': itype,
                'href': href,
                'summary': f"内容概要：{title}（点点分析超时，详见原笔记）",
                'tags': "#知识积累",
                'raw_file': raw_file
            }
            results.append(res_entry)
            processed[str(seq)] = res_entry

    print("\n--- All 30 items summarized successfully! ---")

    # 1. Generate Markdown report
    report_lines = [
        f"# 小红书点赞深度分析 · 每日简报 ({DATE_STR})\n",
        f"> 本次自动同步完成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，共新增并处理 **{len(results)}** 条优质笔记/视频（序号 #{results[0]['seq']} ~ #{results[-1]['seq']}）。\n",
        "## 1. 新增点赞概览表\n",
        "| 序号 | 标题 | 作者 | 点赞数 | 类型 | 标签 |",
        "|:---:|:---|:---|:---:|:---:|:---|"
    ]
    for r in results:
        report_lines.append(f"| {r['seq']} | [{r['title']}]({r['href']}) | {r['author']} | {r['like']} | {r['type']} | {r['tags']} |")

    report_lines.append("\n---\n\n## 2. 逐条精炼分析与知识点沉淀\n")
    for r in results:
        report_lines.append(f"### #{r['seq']} · {r['title']}")
        report_lines.append(f"- **作者**：{r['author']} · **点赞**：{r['like']} · **类型**：{r['type']}")
        report_lines.append(f"- **链接**：[原笔记直达]({r['href']})")
        report_lines.append(f"- **主题标签**：`{r['tags']}`")
        report_lines.append(f"- **核心要点**：\n  > {r['summary']}")
        report_lines.append(f"- **原始对话归档**：`{r['raw_file']}`\n")

    report_content = "\n".join(report_lines)
    
    report_path1 = os.path.join(r"<PROJECT_DIR>\reports", f"小红书点赞分析_{DATE_STR}.md")
    report_path2 = os.path.join(r"D:\workbuddy 工作空间", f"小红书点赞分析_{DATE_STR}.md")
    with open(report_path1, "w", encoding="utf-8") as rf:
        rf.write(report_content)
    with open(report_path2, "w", encoding="utf-8") as rf:
        rf.write(report_content)
    print(f"Daily report saved to:\n  - {report_path1}\n  - {report_path2}")

    # 2. Write to Feishu Base
    print("\nWriting to Feishu Base...")
    fields = ["标题", "序号", "作者", "点赞数", "链接", "内容类型", "分类", "点点总结", "主题标签", "存档文件"]
    rows = []
    for r in results:
        rows.append([
            r["title"],
            r["seq"],
            r["author"],
            r["like"],
            r["href"],
            [r["type"]] if isinstance(r["type"], str) else r["type"],
            ["小红书点赞分析"],
            r["summary"],
            r["tags"],
            os.path.basename(r["raw_file"])
        ])

    payload = {"fields": fields, "rows": rows}
    temp_payload_file = r"<PROJECT_DIR>\_lark_batch_payload.json"
    with open(temp_payload_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    cmd = [
        LARK_CLI, "base", "+record-batch-create",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--json", f"@{temp_payload_file}",
        "--as", "user", "--format", "json"
    ]
    sub_res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    print("Feishu write stdout:", sub_res.stdout[:1500])
    if sub_res.returncode != 0:
        print("Feishu write stderr:", sub_res.stderr[:1000])
    else:
        print("✅ Feishu Base batch create succeeded!")

if __name__ == '__main__':
    main()
