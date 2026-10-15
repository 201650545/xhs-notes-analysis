# -*- coding: utf-8 -*-
"""网关冒烟测试：fast 模型单次 chat completions"""
import json, urllib.request

body = json.dumps({
    "model": "fast",
    "messages": [{"role": "user", "content": '只输出一行JSON: {"verdict":"keep","reason":"smoke test"}'}],
    "max_tokens": 100, "temperature": 0.2}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:3100/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json",
                                      "Authorization": "Bearer gyt2005228"})
raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
print(raw[:1500])
