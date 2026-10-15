# -*- coding: utf-8 -*-
"""本地私有凭证加载器。

真实值存在 _系统数据/_credentials.json（已 .gitignore 排除，不随公开仓库推送）。
本模块作为 fallback 提供公开占位符，保证外部克隆仓库可正常运行而不泄露任何敏感信息。

用法：from _credentials import get_cred
      LARK_BASE_TOKEN = get_cred("FEISHU_BASE_TOKEN", "<FEISHU_BASE_TOKEN>")
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CRED_PATH = os.path.join(BASE, "_系统数据", "_credentials.json")
_cache = None


def _load():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_CRED_PATH, encoding="utf-8-sig") as f:
            _cache = json.load(f)
    except Exception:
        _cache = {}
    return _cache


def get_cred(key, fallback=""):
    return _load().get(key, fallback)