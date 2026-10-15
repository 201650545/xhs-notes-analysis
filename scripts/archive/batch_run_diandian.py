import json
import os
import re
import sys
import time
import urllib.request

BASE_URL = "http://127.0.0.1:10086/command"
OUTPUT_DIR = "D:/workbuddy 工作空间/点点分析结果/raw_20260922"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def send_cmd(action, args=None, session=None, timeout=25):
    payload = {"action": action, "args": args or {}}
    if session:
        payload["session"] = session
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE_URL, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def ask_diandian(note_url):
    prompt = f"请帮我总结这篇小红书笔记：{note_url}"
    
    # 1. 填充输入框
    fill_res = send_cmd("fill", {
        "selector": "textarea",
        "value": prompt
    })
    time.sleep(0.8)

    # 2. 触发提交 (Enter 键 + 点击提交按钮)
    send_cmd("evaluate", {
        "code": """
        (() => {
            const ta = document.querySelector('textarea');
            if (ta) {
                ta.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                    bubbles: true, cancelable: true
                }));
            }
            const submitBtn = document.querySelector('.bottom-box-right-submit-button svg') || document.querySelector('.bottom-box-right-submit-button');
            if (submitBtn) {
                submitBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                submitBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                submitBtn.click();
            }
        })()
        """
    })

    # 3. 轮询等待生成完成（点点打字生成，通常 10-15 秒）
    # 当打字完成时，输入框重新变为可用状态，或者回答文本连续 2 次采样长度稳定
    time.sleep(8)
    last_len = 0
    stable_count = 0
    answer_text = ""

    for attempt in range(10): # 最多再轮询 10 次，每次 1.5s
        res = send_cmd("evaluate", {
            "code": """
            (() => {
                const nodes = Array.from(document.querySelectorAll('.markdown, [class*="chat-message"], [class*="chat-item"], [class*="bubble"]'));
                if (!nodes.length) return "";
                return nodes[nodes.length - 1].innerText.trim();
            })()
            """
        })
        curr_text = res.get("data", {}).get("value", "")
        if len(curr_text) > 30 and len(curr_text) == last_len:
            stable_count += 1
            if stable_count >= 2:
                answer_text = curr_text
                break
        else:
            stable_count = 0
            last_len = len(curr_text)
        time.sleep(1.5)

    if not answer_text and last_len > 0:
        answer_text = curr_text

    return answer_text

def main():
    print(">>> [启动] 读取增量笔记清单...")
    with open("D:/Work/小红书点赞分析/_new_items.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    max_seq = data.get("max_seq", 88)
    items = data.get("new_items", [])
    total = len(items)
    print(f">>> 基准序号: {max_seq}，待处理增量笔记: {total} 篇")

    # 确定按时间从旧到新（89 -> 118）
    # 在 _new_items.json 中，index 0 是最新，index -1 是最旧。
    # 按照惯例，时间正序从最旧到最新编号：
    ordered_items = list(reversed(items))

    # 确保当前在 ai_chat 页面
    print(">>> [检查] 导航到 ai_chat 页面...")
    send_cmd("navigate", {"url": "https://www.xiaohongshu.com/ai_chat", "newTab": False})
    time.sleep(3)

    results = []
    for idx, it in enumerate(ordered_items, 1):
        seq = max_seq + idx
        nid = it["id"]
        title = it["title"]
        author = it.get("author", "")
        href = it.get("href", f"https://www.xiaohongshu.com/explore/{nid}")

        raw_file = os.path.join(OUTPUT_DIR, f"raw_{seq}_{nid}.txt")
        
        # 如果已经存在且有内容，则跳过（支持断点续传）
        if os.path.exists(raw_file) and os.path.getsize(raw_file) > 100:
            print(f"[{idx}/{total}] #{seq} 已存在缓存，跳过: {title[:20]}")
            with open(raw_file, "r", encoding="utf-8") as rf:
                it["summary"] = rf.read()
            it["seq"] = seq
            results.append(it)
            continue

        print(f"\n[{idx}/{total}] 正在处理 #{seq} [{it.get('type', '笔记')}] {title[:25]} (作者: {author})...")
        try:
            summary = ask_diandian(href)
            if not summary or len(summary) < 30:
                # 尝试用短链接 fallback
                short_url = f"https://www.xiaohongshu.com/explore/{nid}"
                summary = ask_diandian(short_url)

            print(f"    √ 成功获取总结，字数: {len(summary)}")
            with open(raw_file, "w", encoding="utf-8") as wf:
                wf.write(summary)

            it["summary"] = summary
            it["seq"] = seq
            results.append(it)
        except Exception as e:
            print(f"    × 出现异常: {e}")

        # 单篇间隔 2 秒，保持节奏
        time.sleep(2)

    # 暂存全量结果
    with open("D:/Work/小红书点赞分析/_summarized_items.json", "w", encoding="utf-8") as sf:
        json.dump({"total": len(results), "items": results}, sf, ensure_ascii=False, indent=2)

    print(f"\n>>> [完成] 全部 {len(results)} 篇笔记总结已保存至 {OUTPUT_DIR}！")

if __name__ == '__main__':
    main()
