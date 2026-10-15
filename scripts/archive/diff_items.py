import os, sys as _s
_s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _credentials import get_cred  # noqa: E402
import json, re

UID = get_cred("XHS_USER_ID", "<XHS_USER_ID>")

def extract_note_id(link):
    if not link:
        return None
    m = re.search(r'/explore/([0-9a-f]{24})', link)
    if m:
        return m.group(1)
    ids = re.findall(r'([0-9a-f]{24})', link)
    for i in ids:
        if i != UID:
            return i
    return None

try:
    with open('D:/Work/小红书点赞分析/_feishu_existing.json', 'r', encoding='utf-16') as f:
        feishu_raw = json.load(f)
except Exception:
    with open('D:/Work/小红书点赞分析/_feishu_existing.json', 'r', encoding='utf-8-sig') as f:
        feishu_raw = json.load(f)

records = feishu_raw.get('data', {}).get('data', [])
print('Total Feishu records:', len(records))

max_seq = 0
existing_ids = set()
existing_titles = set()

for row in records:
    if len(row) > 3 and isinstance(row[3], (int, float)):
        if row[3] > max_seq:
            max_seq = int(row[3])
    if len(row) > 0 and row[0]:
        existing_titles.add(str(row[0]).strip())
    if len(row) > 7 and row[7]:
        nid = extract_note_id(str(row[7]))
        if nid:
            existing_ids.add(nid)

print('Max seq in Feishu:', max_seq)
print('Existing IDs in Feishu:', len(existing_ids))

with open('D:/Work/小红书点赞分析/_liked_list_latest.json', 'r', encoding='utf-8') as f:
    liked_data = json.load(f)

new_items = []
# Maintain chronological order: oldest to newest for sequence numbering (reverse of liked list)
for it in liked_data.get('items', []):
    nid = it['id']
    title = it['title'].strip()
    if nid not in existing_ids and title not in existing_titles:
        new_items.append(it)

print('New items count:', len(new_items))
for idx, it in enumerate(new_items, 1):
    print(f" {idx}. [{it.get('type', '笔记')}] {it['title']} (id: {it['id']}, author: {it['author']}, like: {it['like']})")

with open('D:/Work/小红书点赞分析/_new_items.json', 'w', encoding='utf-8') as f:
    json.dump({'max_seq': max_seq, 'new_items': new_items}, f, ensure_ascii=False, indent=2)
