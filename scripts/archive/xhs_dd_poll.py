# -*- coding: utf-8 -*-
import json, time, urllib.request

API = "http://127.0.0.1:10086/command"
def ev(code):
    body = json.dumps({"action":"evaluate","args":{"code":code}}).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={"Content-Type":"application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    return r["data"]["value"] if r.get("ok") else "ERR:"+json.dumps(r.get("error"))

def lastmsg():
    return ev("(function(){var m=[...document.querySelectorAll('.ai-message')];var l=m[m.length-1];return l?(l.innerText||'').trim():'';})()")

import re
def complete(txt):
    # 占位符或过于简短 -> 未完成
    if not txt: return False
    ph = ["问题分析中", "思考中", "正在总结", "...", "分析中"]
    if any(p in txt for p in ph) and len(txt) < 20:
        return False
    return len(txt) > 30

last = ""
stable = 0
for i in range(50):
    txt = lastmsg()
    if complete(txt):
        if txt == last:
            stable += 1
        else:
            stable = 0
        last = txt
        if stable >= 2:
            print("DONE len", len(txt))
            print(txt)
            break
    time.sleep(2)
print("FINAL len", len(last))