import sqlite3
import json
import os

db_path = r'C:\Users\郭永涛\.local\share\opencode\opencode.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def get_session_transcript(session_id):
    cursor.execute('''
        SELECT m.id, m.time_created, m.data, p.data, p.time_created
        FROM message m
        JOIN part p ON m.id = p.message_id
        WHERE m.session_id = ?
        ORDER BY m.time_created ASC, p.time_created ASC;
    ''', (session_id,))
    rows = cursor.fetchall()
    entries = []
    for mid, mtc, mdata, pdata, ptc in rows:
        md = json.loads(mdata) if mdata else {}
        pd = json.loads(pdata) if pdata else {}
        role = md.get('role', 'unknown')
        part_type = pd.get('type', '')
        text = pd.get('text', '')
        tool_name = pd.get('name', '')
        tool_input = pd.get('state', {}).get('input', {})
        entries.append({
            'role': role,
            'type': part_type,
            'text': text,
            'tool_name': tool_name,
            'tool_input': tool_input,
            'time': ptc or mtc
        })
    return entries

out_dir_work = r'D:\Work\小红书点赞分析\会话记录导出'
out_dir_desk = r'D:\360MoveData\Users\郭永涛\Desktop\OpenCode会话记录'
os.makedirs(out_dir_work, exist_ok=True)
os.makedirs(out_dir_desk, exist_ok=True)

# 1. 导出 积压一审
review_sessions = [
    ('ses_ecfc2723effe9LkURfR73g7uot', '积压一审A组（11篇初审）'),
    ('ses_ecfc271fdffeTBnPotm45Sy6AJ', '积压一审B组（10篇初审）')
]

review_md = ['# 小红书笔记积压一审 A/B 组及三审决议完整记录\n']
review_md.append('> 导出时间：2026-10-13 00:05\n> 关联项目：`D:\\Work\\小红书点赞分析`\n\n---\n')

for sid, title in review_sessions:
    review_md.append(f'## 一、{title} (Session ID: `{sid}`)\n\n')
    t = get_session_transcript(sid)
    for item in t:
        r = item['role'].upper()
        if item['type'] == 'text' and item['text']:
            review_md.append(f'### 【{r}】\n\n{item["text"]}\n\n')
        elif item['type'] == 'tool' and item['tool_name']:
            review_md.append(f'**[调用工具 {item["tool_name"]}]**\n```json\n{json.dumps(item["tool_input"], ensure_ascii=False, indent=2)}\n```\n\n')

# 追加主会话中最后的决议与争议裁定
review_md.append('## 二、主会话裁决记录与 21 篇三审入账 (Session: `ses_ee0157e58ffevh5Nl1Fg6YYO8j`)\n\n')
cursor.execute('''
    SELECT m.time_created, m.data, p.data
    FROM message m
    JOIN part p ON m.id = p.message_id
    WHERE m.session_id = 'ses_ee0157e58ffevh5Nl1Fg6YYO8j'
    ORDER BY m.time_created DESC
    LIMIT 35;
''')
parent_rows = cursor.fetchall()
parent_rows.reverse()
for mtc, mdata, pdata in parent_rows:
    md = json.loads(mdata) if mdata else {}
    pd = json.loads(pdata) if pdata else {}
    role = md.get('role', 'unknown').upper()
    text = pd.get('text', '')
    if text:
        review_md.append(f'### 【{role}】\n\n{text}\n\n')

# 附录相关临时文件
for fn in ['xhs_batch1_merged.json', 'xhs_batch1_out0.json', 'xhs_batch1_out1.json']:
    fp = os.path.join(r'C:\Users\郭永涛\AppData\Local\Temp', fn)
    if os.path.exists(fp):
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        review_md.append(f'## 附录数据：{fn}\n\n```json\n{content}\n```\n\n')

content_review = '\n'.join(review_md)
with open(os.path.join(out_dir_work, '01_积压一审_AB组及三审决议完整记录.md'), 'w', encoding='utf-8') as f:
    f.write(content_review)
with open(os.path.join(out_dir_desk, '01_积压一审_AB组及三审决议完整记录.md'), 'w', encoding='utf-8') as f:
    f.write(content_review)

print('Exported Review MD successfully.')

# 2. 导出 艾丽方法论提炼
eli_sessions = [
    ('ses_ed43312ccffeUehISDiKUfqXVP', '艾丽方法论提炼A组（前10篇）'),
    ('ses_ed437d862ffeHSqMksVQv2D0pT', '艾丽方法论提炼B组（中10篇）'),
    ('ses_ed437d841ffeAVfkvCsnGUZHcW', '艾丽方法论提炼C组（后9篇）')
]

eli_md = ['# 艾丽方法论提炼 A/B/C 组完整记录\n']
eli_md.append('> 导出时间：2026-10-13 00:05\n> 关联项目：`D:\\Work\\小红书点赞分析\\_系统数据\\ela_notes`\n\n---\n')

for sid, title in eli_sessions:
    eli_md.append(f'## 一、{title} (Session ID: `{sid}`)\n\n')
    t = get_session_transcript(sid)
    for item in t:
        r = item['role'].upper()
        if item['type'] == 'text' and item['text']:
            eli_md.append(f'### 【{r}】\n\n{item["text"]}\n\n')
        elif item['type'] == 'tool' and item['tool_name']:
            eli_md.append(f'**[调用工具 {item["tool_name"]}]**\n```json\n{json.dumps(item["tool_input"], ensure_ascii=False, indent=2)}\n```\n\n')

for fn in ['ela_method_A.json', 'ela_method_B.json', 'ela_method_C.json']:
    fp = os.path.join(r'C:\Users\郭永涛\AppData\Local\Temp', fn)
    if os.path.exists(fp):
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        eli_md.append(f'## 附录方法论提炼结果：{fn}\n\n```json\n{content}\n```\n\n')

content_eli = '\n'.join(eli_md)
with open(os.path.join(out_dir_work, '02_艾丽方法论提炼_ABC组完整记录.md'), 'w', encoding='utf-8') as f:
    f.write(content_eli)
with open(os.path.join(out_dir_desk, '02_艾丽方法论提炼_ABC组完整记录.md'), 'w', encoding='utf-8') as f:
    f.write(content_eli)

print('Exported Eli MD successfully.')
conn.close()
