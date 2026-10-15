# -*- coding: utf-8 -*-
"""最后2篇：改输入指纹（全文3000字+temp0.7）破缓存拿完整JSON"""
import json, urllib.request, re

SHORT_SYS = ("你是小红书笔记筛选二审员。用户是小学心理健康教育老师＋AI开发者，"
             "判定轴：连接他自己系统的留，纯外部世界的删。保留：1已落地 2方法论 3可迁移技术 "
             "4稀缺程序知识 5顶级AI方法论 7心理三观 8可改造基座 9赚钱变现；删除：1过时 2花钱折腾 "
             "3软广 4无关 5高风险 9炫技 10场景性 11搜得到的操作 14通用科普 21英语备考。"
             "只输出一行JSON：{\"verdict\":\"keep|drop\",\"reason\":\"≤30字，引用判据编号\"}。")

out = []
for nid, ncut in [("6a70512800000000060066a3", 3000), ("6ab79ef300000000150042cb", 3000)]:
    note = open(r"D:\Work\小红书点赞分析\b_answers\%s.txt" % nid, encoding="utf-8").read()[:ncut]
    body = json.dumps({"model": "fast",
                       "messages": [{"role": "system", "content": SHORT_SYS},
                                    {"role": "user", "content": "全文如下（请判定，只输出一行JSON）：\n%s" % note}],
                       "max_tokens": 800, "temperature": 0.7}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:3100/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer gyt2005228"})
    try:
        raw = urllib.request.urlopen(req, timeout=180).read().decode("utf-8", "ignore")
        resp = json.loads(raw)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content") or ""
        print("=" * 40, nid, "model:", resp.get("model"))
        print("CONTENT:", content[:600])
        m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', content)
        if m:
            j = json.loads(m.group(0))
            if j.get("verdict") in ("keep", "drop"):
                out.append({"id": nid, "verdict": j["verdict"], "reason": j.get("reason", "") + "（短理由补采）"})
                continue
        out.append({"id": nid, "err": "no_json", "raw": content[:300]})
    except Exception as e:
        print(nid, "请求异常:", str(e)[:200])
        out.append({"id": nid, "err": str(e)[:120]})

json.dump(out, open(r"D:\Work\小红书点赞分析\_系统数据\second_patch.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("落盘:", out)
