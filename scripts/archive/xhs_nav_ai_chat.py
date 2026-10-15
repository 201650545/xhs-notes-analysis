import json, urllib.request

def call(action, args, session="xhs"):
    body = json.dumps({"action": action, "args": args, "session": session}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:10086/command", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

result = call("navigate", {"url": "https://www.xiaohongshu.com/ai_chat"})
print(json.dumps(result, ensure_ascii=False, indent=2))
