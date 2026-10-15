# -*- coding: utf-8 -*-
"""最后2顽固篇手动单发诊断"""
import json, urllib.request

SYSTEM = open(r"D:\Work\小红书点赞分析\scripts\judge_gateway.py", encoding="utf-8").read()
SYSTEM = SYSTEM.split('SYSTEM = """')[1].split('"""')[0]

for nid in ["6a70512800000000060066a3", "6ab79ef300000000150042cb"]:
    note = open(r"D:\Work\小红书点赞分析\b_answers\%s.txt" % nid, encoding="utf-8").read()[:5000]
    body = json.dumps({"model": "free-flash",
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": "笔记全文：\n%s\n\n按判据判定，只输出 JSON。" % note}],
                       "max_tokens": 1200, "temperature": 0.2}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:3100/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer gyt2005228"})
    try:
        raw = urllib.request.urlopen(req, timeout=150).read().decode("utf-8", "ignore")
        resp = json.loads(raw)
        ch = resp.get("choices", [{}])[0].get("message", {})
        print("=" * 40, nid)
        print("model:", resp.get("model"), "finish:", resp.get("choices", [{}])[0].get("finish_reason"))
        print("CONTENT:", repr(ch.get("content"))[:2500])
    except Exception as e:
        print(nid, "请求异常:", str(e)[:200])
