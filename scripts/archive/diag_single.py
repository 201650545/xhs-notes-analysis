# -*- coding: utf-8 -*-
"""单篇诊断：完整打印网关对 6aba6a39 的原始响应"""
import json, urllib.request

nid = "6aba6a39" + "000000001b02c8a6"
note = open(r"D:\Work\小红书点赞分析\b_answers\%s.txt" % nid, encoding="utf-8").read()[:5000]
print("全文长度:", len(note))
sys_prompt = "你是小红书笔记筛选二审员。只输出一行 JSON：{\"verdict\":\"keep|drop\",\"reason\":\"一句话理由\"}"
body = json.dumps({"model": "fast",
                   "messages": [{"role": "system", "content": sys_prompt},
                                {"role": "user", "content": "笔记全文：\n%s\n\n按判据判定，只输出 JSON。" % note}],
                   "max_tokens": 500, "temperature": 0.2}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:3100/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json",
                                      "Authorization": "Bearer gyt2005228"})
raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "ignore")
print("HTTP 200, 原始响应:")
print(raw[:3000])
