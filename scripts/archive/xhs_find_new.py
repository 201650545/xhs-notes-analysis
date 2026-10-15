import json

with open(r"D:\workbuddy 工作空间\_liked_list_20260903_clean.json", "r", encoding="utf-8") as f:
    liked = json.load(f)

with open(r"D:\workbuddy 工作空间\_lark_existing_20260903.json", "r", encoding="utf-8") as f:
    existing = json.load(f)

existing_ids = set(r["note_id"] for r in existing["records"] if r["note_id"])
print("existing ids:", len(existing_ids))

new_items = []
for it in liked["items"]:
    if it["id"] not in existing_ids:
        new_items.append(it)

print("new count:", len(new_items))
for i, it in enumerate(new_items, 1):
    print(i, "|", it["id"], "|", it["title"], "|", it["author"], "|", it["like"])

with open(r"D:\workbuddy 工作空间\_new_items_20260903.json", "w", encoding="utf-8") as f:
    json.dump({"new_items": new_items, "start_seq": existing["max_seq"] + 1}, f, ensure_ascii=False, indent=2)
