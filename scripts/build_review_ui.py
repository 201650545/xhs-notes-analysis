# -*- coding: utf-8 -*-
"""
build_review_ui.py — 一审批次 TSV → 二审判决台（单文件、零依赖 HTML，4:3 滑卡）

用法:
  python build_review_ui.py --input <批次.tsv> --output <判决台.html> [--batch 批次名] [--demo]

TSV 格式（首行表头，UTF-8，Tab 分隔，单元格内不要换行/Tab）:
  id          24 位笔记 ID
  title       笔记标题
  category    大类字母 A-G（可空）
  suggestion  一审建议: keep | drop | dispute（争议=倾向删）
  reason      一审判决理由（为什么建议留/删，单行）
  what        笔记总结①：这篇大概讲什么（单行）
  use         笔记总结②：有什么用途/怎么用（单行）
  fulltext    全文路径，相对项目根或绝对路径；"-" 或留空 = 无全文
  （旧 TSV 无 what/use 列也能跑，总结区不显示）

交互：一次一张 4:3 卡。左滑/←=删，右滑/→=留，上滑/↑=返回上一条重判。
信息层级（自上而下）：①一审建议+判决理由（最大最醒目）②笔记讲什么/有什么用 ③标题/元信息 ④全文备查。
判决台只产生 verdict JSON，不删任何东西；删除仍走 multi-store-sync-delete 流程。
"""
import argparse, csv, json, os, sys, datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_LIMIT = 20000

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>二审判决台 · __BATCH_NAME__</title>
<style>
/* ============================================================
   二审判决台 · 样式表（2026-10-10 重设计）
   设计目标：昼夜双主题 / 易读排版 / 简约 / 轻交互 / 代码整洁
   结构：① 令牌 ② 基础骨架 ③ 页头 ④ 卡片 ⑤ 建议条 ⑥ 总结
        ⑦ 全文 ⑧ 盖章与飞离 ⑨ 底座与键位 ⑩ 总览 ⑪ 浮层与完成页
        ⑫ 摄像头 / 语音 / 暂停
   约定：颜色/圆角/阴影/动效一律走令牌，组件块内不写死颜色；
        JS 依赖的类名一个不改（swipe-card、card-v 系列、verdict 与 v- 系列、
        s- 系列、oval、ov- 系列）。注意：注释文字里严禁出现星斜杠相邻序列。
   ============================================================ */

/* ① 令牌 ——— 暗色为默认（无 JS 时也成立）；亮色由 data-theme 覆盖 */
:root{
  /* 面色 */
  --bg:#0f1013;          --card:#16171c;       --card-2:#1c1d24;
  --ink:#ececee;         --ink-2:#a6a7b0;      --ink-3:#75767f;
  --hair:rgba(255,255,255,.08);   --hair-2:rgba(255,255,255,.15);
  --tag-bg:rgba(255,255,255,.055);
  /* 判定色（ verdict 实心块：低饱和底 + 高饱和块，白字） */
  --keep:#33b98b;  --keep-deep:#0d7a56;  --keep-soft:rgba(51,185,139,.12);
  --drop:#d6475f;  --drop-deep:#8f2334;  --drop-soft:rgba(214,71,95,.12);
  --amber:#c8963a; --amber-soft:rgba(200,150,58,.12);
  --keep-solid:#14996a; --drop-solid:#bd2d45; --amber-solid:#a3741a;
  /* 纸墨撞色：摘要区＝暖纸块（暗色下与炭灰卡面对撞），金线＝高级感勾边 */
  --paper:#f1ece0; --paper-ink:#23252b; --paper-ink-2:#5a5d66; --paper-hair:rgba(35,37,43,.16);
  --gold:#c6a25e;
  /* 形状与材质 */
  --r-lg:20px; --r-md:14px; --r-sm:10px;
  --shadow:0 24px 60px -26px rgba(0,0,0,.6);
  --kbd-bg:#23252c;
  /* 字体 */
  --sans:-apple-system,BlinkMacSystemFont,"PingFang SC","HarmonyOS Sans SC","MiSans","Microsoft YaHei","Segoe UI",sans-serif;
  --serif:"Noto Serif SC","Source Han Serif SC","Songti SC","STZhongsong",Georgia,serif;
  --mono:ui-monospace,"Cascadia Code",Consolas,monospace;
  /* 动效 */
  --ease:cubic-bezier(.32,.72,0,1);
  --dur:160ms;
}
:root[data-theme="light"]{
  --bg:#f4f3f0;          --card:#ffffff;       --card-2:#faf9f7;
  --ink:#26282d;         --ink-2:#61656d;      --ink-3:#8e9198;
  --hair:rgba(22,24,30,.10);        --hair-2:rgba(22,24,30,.18);
  --tag-bg:rgba(22,24,30,.05);
  --keep:#0e8f62;  --keep-deep:#0a6b4a;  --keep-soft:rgba(14,143,98,.09);
  --drop:#bf3448;  --drop-deep:#8f2334;  --drop-soft:rgba(191,52,72,.08);
  --amber:#96690f; --amber-soft:rgba(150,105,15,.10);
  --keep-solid:#0b7a54; --drop-solid:#a82638; --amber-solid:#7e5a0d;
  --paper:#fdfbf4; --paper-ink:#26282d; --paper-ink-2:#63676f; --paper-hair:rgba(38,40,45,.16);
  --gold:#b8945a;
  --shadow:0 20px 48px -26px rgba(28,30,38,.28);
  --kbd-bg:#ffffff;
}

/* ② 基础骨架 */
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
html{background:var(--bg)}
body{margin:0;color:var(--ink);overscroll-behavior:none;
  font:17px/1.75 var(--sans);background:var(--bg);
  display:flex;flex-direction:row;min-height:100vh;
  transition:background var(--dur),color var(--dur)}
button{font:inherit;color:var(--ink);cursor:pointer;border:none;background:none}

/* ③ 页头 */
header{flex:0 0 auto;padding:16px 0 8px}
.wrap{max-width:880px;width:100%;margin:0 auto;padding:0 20px}
.row1{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
h1{font-family:var(--serif);font-size:19px;margin:0;font-weight:900;letter-spacing:.5px;
  display:flex;align-items:center;gap:9px;white-space:nowrap}
h1::before{content:"";width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:var(--drop)}
.demotag{background:var(--drop-soft);color:var(--drop);border:1px solid var(--hair-2);
  font-size:11px;font-weight:800;letter-spacing:.12em;padding:2.5px 10px;border-radius:999px;white-space:nowrap}
.spacer{flex:1}
.counts{font-size:13.5px;color:var(--ink-2);display:flex;gap:14px;white-space:nowrap;align-items:baseline}
.counts b{font-family:var(--mono);font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}
.c-keep{color:var(--keep)} .c-drop{color:var(--drop)}
.progress{height:6px;border-radius:999px;overflow:hidden;display:flex;background:var(--tag-bg);margin:12px 0 0}
.progress i{display:block;height:100%;transition:width .45s var(--ease)}
.p-keep{background:var(--keep)} .p-drop{background:var(--drop)} .p-pending{background:var(--tag-bg)}
/* 左侧竖向功能区 */
.side{flex:0 0 auto;width:84px;padding:14px 10px;display:flex;flex-direction:column;
  border-right:1px solid var(--hair);background:var(--bg)}
.col{flex:1 1 auto;display:flex;flex-direction:column;min-width:0;min-height:0}
.menu{display:flex;flex-direction:column;gap:9px;align-items:stretch;height:100%;margin:0}
.menu button{font-size:12.5px;font-weight:600;padding:9px 4px;border-radius:var(--r-sm);
  width:100%;line-height:1.3;text-align:centerpx;
  border:1px solid var(--hair);background:var(--tag-bg);color:var(--ink-2);
  transition:color var(--dur),border-color var(--dur),background var(--dur)}
.menu button:hover{color:var(--ink);border-color:var(--hair-2)}
.menu button.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.menu button.primary{background:var(--drop);border-color:var(--drop);color:#fff;font-weight:700}
.menu button.primary:hover{background:var(--drop-deep)}
.demoline{margin-top:10px;font-size:12.5px;line-height:1.6;color:var(--drop);background:var(--drop-soft);
  border:1px solid var(--hair-2);border-left:3px solid var(--drop);border-radius:var(--r-sm);
  padding:8px 12px;display:none}
body.demo .demoline{display:block}

/* ④ 卡片 */
main{flex:1 1 auto;display:flex;flex-direction:column;min-height:0;padding:12px 20px 4px}
.stage{flex:1 1 auto;position:relative;display:flex;align-items:stretch;justify-content:center;min-height:0;padding:0}
.swipe-card{position:relative;height:100%;width:min(1020px,100%);aspect-ratio:auto;max-width:100%;margin:auto;
  overflow:hidden;background:var(--card);border:1px solid var(--hair);border-radius:var(--r-lg);
  touch-action:none;cursor:grab;box-shadow:var(--shadow);
  display:flex;flex-direction:column;color:var(--ink);
  transition:background var(--dur)}
.swipe-card.grabbing{cursor:grabbing}
.swipe-card.enter{animation:cardIn .34s cubic-bezier(.22,1.1,.32,1)}
.swipe-card.back{animation:cardBack .3s var(--ease)}
@keyframes cardIn{from{opacity:0;transform:translateY(22px) scale(.97)}to{opacity:1;transform:none}}
@keyframes cardBack{from{opacity:.35;transform:translateY(-12px) scale(.98)}to{opacity:1;transform:none}}
.swipe-card.fly-drop{transition:transform .3s cubic-bezier(.5,0,.8,.4),opacity .3s;transform:translateX(-135%) rotate(-14deg);opacity:0}
.swipe-card.fly-keep{transition:transform .3s cubic-bezier(.5,0,.8,.4),opacity .3s;transform:translateX(135%) rotate(14deg);opacity:0}
/* 元信息行 = 身份条：居中排布（对称构图的上沿），细分隔线，标题加重 */
.meta{flex:0 0 auto;display:flex;align-items:center;justify-content:center;gap:9px;padding:15px 24px 11px;
  font-size:13px;color:var(--ink-3);border-bottom:1px solid var(--hair)}
.meta .idx{font-weight:700;color:var(--ink-2);font-family:var(--mono);font-size:12.5px}
.meta .cat{background:var(--tag-bg);border:1px solid var(--hair);border-radius:999px;
  padding:2px 10px;font-weight:600;color:var(--ink-2)}
.meta .title{flex:0 1 auto;min-width:0;font-size:15.5px;font-weight:700;color:var(--ink);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meta .now{font-size:12px;font-weight:700;padding:2.5px 11px;border-radius:999px;color:#fff;display:none}
.card-v-keep .meta .now{display:block;background:var(--keep-deep)}
.card-v-drop .meta .now{display:block;background:var(--drop-deep)}

/* ⑤ 一审建议条 = 通栏实心色块 · 居中印章构图（对称美学主焦点）
   纸墨逻辑：色块取判定实色、白字；上下用金线勾边，块内元素全部居中对齐 */
.verdict{flex:0 0 auto;position:relative;margin:0;padding:20px 24px 18px;
  display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;
  border-top:1px solid var(--gold);border-bottom:1px solid var(--gold)}
.verdict::after{content:"一审预判";position:absolute;top:10px;right:16px;
  font-size:10px;font-weight:700;letter-spacing:.22em;color:rgba(255,255,255,.55)}
.verdict .v-ico{width:50px;height:50px;border-radius:12px;display:flex;
  align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#fff;
  font-family:var(--serif);background:rgba(255,255,255,.16);border:1.5px solid rgba(255,255,255,.4)}
.verdict .v-main{min-width:0}
.verdict .v-label{font-family:var(--serif);font-size:32px;font-weight:900;letter-spacing:7px;line-height:1.25;color:#fff}
.verdict .v-label small{font-family:var(--sans);font-size:11px;font-weight:800;letter-spacing:.14em;
  margin-left:12px;vertical-align:3px;opacity:.8;border:1px solid rgba(255,255,255,.55);
  border-radius:999px;padding:1.5px 8px;color:#fff}
.verdict .v-reason{margin:2px auto 0;max-width:58ch;font-size:16.5px;line-height:1.75;color:rgba(255,255,255,.88)}
.verdict.v-keep{background:var(--keep-solid)}
.verdict.v-drop{background:var(--drop-solid)}
.verdict.v-dispute{background:var(--amber-solid)}

/* ⑥ 笔记总结 = 暖纸块：与上下色面对撞，金线勾边＋纸纹（质感来源） */
.summary{flex:1 1 auto;min-height:0;overflow:auto;margin:16px;padding:16px 20px 18px;
  background:var(--paper);color:var(--paper-ink);border:1px solid var(--paper-hair);
  border-radius:var(--r-md);box-shadow:0 0 0 1px var(--gold),0 10px 24px -14px rgba(0,0,0,.35);
  scrollbar-width:thin}
.summary::before{content:"摘 要";display:block;text-align:center;font-size:10.5px;font-weight:800;
  letter-spacing:.5em;color:var(--paper-ink-2);margin-bottom:10px;text-indent:.5em}
.s-row{display:flex;gap:13px;align-items:flex-start;font-size:17px;line-height:1.9;color:var(--paper-ink)}
.s-row+.s-row{margin-top:11px;padding-top:11px;border-top:1px solid var(--paper-hair)}
.s-tag{flex:0 0 78px;text-align:center;font-size:12.5px;font-weight:700;color:var(--paper-ink-2);
  background:transparent;border:1px solid var(--paper-hair);border-radius:999px;
  padding:3px 8px;margin-top:3px;letter-spacing:.05em}
.s-row .s-txt{min-width:0;flex:1}
/* 关键细节 / 坑 / 原文一句（纸面内次级层次：题居中等宽金点） */
.d-hd{margin:16px 0 7px;font-size:12px;font-weight:800;letter-spacing:.3em;color:var(--paper-ink-2);text-align:center;text-indent:.3em}
.d-list{margin:0;padding-left:20px}
.d-list li{font-size:16.5px;line-height:1.75;color:var(--paper-ink);margin:0 0 6px}
.d-list li::marker{color:var(--gold)}
.s-tag.cost{color:var(--drop-solid);background:transparent;border-color:var(--drop-solid)}
.cost-txt{color:var(--drop-solid)}
.quote{margin:14px 0 0;padding:11px 15px;border-left:3px solid var(--gold);background:rgba(198,162,94,.14);
  border-radius:0 var(--r-sm) var(--r-sm) 0;font-family:var(--serif);font-size:16.5px;line-height:1.8;color:var(--paper-ink)}
.quote small{display:block;margin-top:5px;font-family:var(--sans);font-size:11px;letter-spacing:.1em;
  color:var(--paper-ink-2)}

/* ⑦ 全文备查 = 墨匣：深色面收底，与纸面对抗；题居中等宽 */
details.ft{flex:0 0 auto;margin:0 16px 16px;border:1px solid var(--hair-2);border-radius:var(--r-md);
  overflow:hidden;background:var(--card-2)}
details.ft summary{cursor:pointer;padding:10px 16px;font-size:12.5px;color:var(--ink-2);
  font-weight:600;user-select:none;touch-action:auto;transition:color var(--dur);
  letter-spacing:.3em;text-align:center;text-indent:.3em}
details.ft summary:hover{color:var(--ink)}
details.ft summary::marker{color:var(--ink-3)}
.fulltext{margin:0;padding:14px 18px;max-height:30vh;overflow:auto;font-size:15.5px;line-height:1.9;
  white-space:pre-wrap;border-top:1px solid var(--hair);touch-action:auto;color:var(--ink-2);
  scrollbar-width:thin}

/* ⑧ 盖章与飞离 */
.stamp{position:absolute;top:36%;font-family:var(--serif);font-size:38px;font-weight:900;letter-spacing:8px;
  padding:2px 16px;border-radius:var(--r-md);opacity:0;pointer-events:none;z-index:5;
  background:var(--card);box-shadow:var(--shadow)}
.stamp.drop{right:26px;color:var(--drop);transform:rotate(12deg);border:3px solid var(--drop)}
.stamp.keep{left:26px;color:var(--keep);transform:rotate(-12deg);border:3px solid var(--keep)}

/* ⑨ 底座与键位 */
/* 底栏按他 2026-10-10 要求隐藏（判定走键盘/语音/手势/左右滑） */
.dock{display:none}
.oval{width:82px;height:82px;border-radius:50%;font-size:32px;font-weight:800;color:#fff;
  display:flex;align-items:center;justify-content:center;font-family:var(--serif);
  transition:transform var(--dur) var(--ease),box-shadow var(--dur),opacity var(--dur)}
.oval:hover{transform:translateY(-2px)}
.oval:active{transform:scale(.92);transition-duration:80ms}
.oval.drop{background:var(--drop);box-shadow:0 12px 28px -12px color-mix(in srgb,var(--drop) 70%,transparent)}
.oval.keep{background:var(--keep);box-shadow:0 12px 28px -12px color-mix(in srgb,var(--keep) 70%,transparent)}
.oval.drop:hover{background:var(--drop-deep)}
.oval.keep:hover{background:var(--keep-deep)}
.oval.back{width:62px;height:62px;font-size:22px;color:var(--ink-2);
  background:var(--card);border:1.5px solid var(--hair-2)}
.oval.back:hover{color:var(--ink)}
.oval.back.armed{color:var(--drop);border-color:var(--drop);background:var(--drop-soft)}
/* 键位说明条一并隐藏（他说“说明按钮隐藏”） */
.keybar{display:none}
.keybar .kb{display:inline-flex;align-items:center;gap:6px;font-weight:600;color:var(--ink-2)}
.keybar kbd{font:13.5px/1 ui-monospace,Consolas,monospace;min-width:25px;height:25px;display:inline-flex;
  align-items:center;justify-content:center;padding:0 7px;border-radius:7px;background:var(--kbd-bg);
  border:1px solid var(--hair-2);border-bottom-width:2.5px;color:var(--ink)}
.keybar kbd.k-drop{color:#fff;background:var(--drop);border-color:var(--drop-deep)}
.keybar kbd.k-keep{color:#fff;background:var(--keep);border-color:var(--keep-deep)}
.keybar .kb-sep{width:1px;height:18px;background:var(--hair-2)}
.keybar .kb-tip{color:var(--ink-3);font-size:12px}

/* ⑩ 总览浮层 */
.ov{position:fixed;inset:0;z-index:80;background:rgba(10,10,14,.55);backdrop-filter:blur(8px);
  -webkit-backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;padding:24px}
.ov[hidden]{display:none}
.ov-panel{width:min(720px,94vw);max-height:82vh;display:flex;flex-direction:column;background:var(--card);
  border-radius:var(--r-lg);box-shadow:var(--shadow);overflow:hidden;border:1px solid var(--hair)}
.ov-head{display:flex;align-items:center;gap:12px;padding:13px 18px;border-bottom:1px solid var(--hair)}
.ov-head b{font-family:var(--serif);font-size:16px;letter-spacing:.5px}
.ov-filters{display:flex;gap:6px;margin-left:auto}
.ov-filters button{font-size:12px;padding:5px 12px;border-radius:999px;border:1px solid var(--hair);
  background:var(--tag-bg);color:var(--ink-2);font-weight:600}
.ov-filters button.on{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.ov-x{font-size:12.5px;padding:5px 14px;border-radius:999px;border:1px solid var(--hair);
  background:var(--tag-bg);color:var(--ink-2)}
.ov-list{overflow:auto;padding:6px;scrollbar-width:thin}
.ov-row{display:flex;align-items:center;gap:10px;width:100%;text-align:left;padding:9px 12px;
  border-radius:var(--r-sm);color:var(--ink);font-size:13.5px}
.ov-row:hover{background:var(--tag-bg)}
.ov-row.cur{background:var(--amber-soft);box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--amber) 45%,transparent)}
.ov-idx{flex:0 0 auto;font:11px/1 var(--mono);color:var(--ink-3);min-width:36px}
.ov-badge{flex:0 0 auto;font-size:11px;font-weight:800;padding:2.5px 9px;border-radius:999px;color:#fff}
.ov-badge.keep{background:var(--keep-deep)} .ov-badge.drop{background:var(--drop-deep)} .ov-badge.pending{background:var(--ink-3)}
.ov-title{flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
.ov-empty{padding:26px;text-align:center;color:var(--ink-3);font-size:13px}

/* ⑪ 浮层与完成页 */
.toast{position:fixed;left:50%;bottom:92px;transform:translateX(-50%) translateY(10px);opacity:0;
  background:var(--card);border:1px solid var(--hair-2);color:var(--ink);padding:9px 20px;border-radius:999px;
  font-size:13px;font-weight:600;pointer-events:none;transition:all .3s var(--ease);z-index:99;
  box-shadow:var(--shadow)}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.done{display:none;width:100%;max-width:460px;margin:auto;text-align:center;
  background:var(--card);border:1px solid var(--hair);border-radius:var(--r-lg);
  box-shadow:var(--shadow);padding:44px 32px 36px}
.done.show{display:block;animation:cardIn .45s cubic-bezier(.22,1.1,.32,1)}
.done .big{font-size:48px;margin-bottom:8px}
.done h2{font-family:var(--serif);margin:0 0 8px;font-size:23px;font-weight:900;letter-spacing:1px}
.done p{color:var(--ink-2);font-size:14.5px;line-height:1.8;margin:0 0 22px}
.done .btns{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.done button{font-size:14px;padding:10px 22px;border-radius:999px;border:1px solid var(--hair-2);
  background:var(--tag-bg);color:var(--ink);font-weight:600}
.done button.primary{background:var(--drop);border-color:var(--drop);color:#fff}

/* ⑫ 摄像头 / 语音 / 暂停 */
.vhud{position:fixed;right:16px;bottom:16px;z-index:60;display:flex;align-items:center;gap:8px;
  background:var(--card);border:1px solid var(--hair-2);color:var(--ink);padding:9px 15px;border-radius:999px;
  font-size:13px;font-weight:600;box-shadow:var(--shadow);max-width:min(360px,60vw)}
.vhud[hidden]{display:none}
.vhud .dot{width:9px;height:9px;border-radius:50%;background:var(--drop);flex:0 0 auto;animation:vpulse 1.2s infinite}
.vhud.on .dot{background:var(--keep)}
@keyframes vpulse{0%,100%{opacity:1}50%{opacity:.3}}
.cam-panel{position:fixed;right:16px;bottom:64px;width:180px;z-index:60;display:none}
.cam-panel.show{display:block;animation:cardIn .25s ease}
.cam-resize{position:absolute;left:-7px;top:-7px;width:20px;height:20px;z-index:6;cursor:nwse-resize;
  border-radius:50%;background:var(--ink);border:2px solid var(--bg);box-shadow:0 3px 8px rgba(0,0,0,.4);touch-action:none}
.cam-resize::after{content:"";position:absolute;left:4px;top:4px;width:8px;height:8px;
  border-left:2.5px solid var(--bg);border-top:2.5px solid var(--bg);border-radius:2px 0 0 0}
.cam-box{position:relative;border-radius:var(--r-md);overflow:hidden;border:2px solid var(--hair-2);
  background:#0e0e14;box-shadow:var(--shadow)}
#cam-video{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;transform:scaleX(-1);background:#0e0e14}
.cam-arr{position:absolute;font-size:24px;color:#fff;text-shadow:0 1px 5px rgba(0,0,0,.7);
  opacity:.28;transition:opacity .1s,transform .1s;pointer-events:none;font-weight:900}
.cam-arr.l{left:7px;top:50%;transform:translateY(-50%)}
.cam-arr.r{right:7px;top:50%;transform:translateY(-50%)}
.cam-arr.u{top:6px;left:50%;transform:translateX(-50%)}
.cam-arr.hot{opacity:1;transform:scale(1.45)}
.cam-arr.l.hot{color:var(--drop);transform:translateY(-50%) scale(1.45)}
.cam-arr.r.hot{color:var(--keep);transform:translateY(-50%) scale(1.45)}
.cam-arr.u.hot{color:#5aa9ff;transform:translateX(-50%) scale(1.45)}
.cam-prog{position:absolute;left:10%;bottom:7px;height:4px;width:80%;border-radius:2px;
  background:rgba(255,255,255,.25);overflow:hidden;display:none}
.cam-prog i{display:block;height:100%;width:0;background:#fff;border-radius:2px}
#cam-dbg{position:absolute;left:6px;right:6px;bottom:15px;font:600 11px/1.5 Consolas,Menlo,monospace;
  color:#fff;text-shadow:0 0 4px #000,0 0 2px #000;white-space:nowrap;overflow:hidden;
  pointer-events:none;text-align:center}
#cam-dbg small{display:block;font-size:9.5px;opacity:.85}
.cam-hint{margin-top:7px;font-size:12px;line-height:1.45;color:#fff;text-align:center;
  background:rgba(14,14,20,.88);border:1px solid var(--hair-2);border-radius:999px;padding:4px 10px}
.cam-modes{display:flex;gap:6px;margin:0 0 6px}
.cam-mode{flex:1;padding:6px 8px;border-radius:var(--r-sm);border:1px solid var(--hair-2);
  background:var(--card);color:var(--ink-2);font-size:12px;font-weight:700;opacity:.65;transition:opacity var(--dur)}
.cam-mode.on{opacity:1;background:var(--ink);color:var(--bg);border-color:var(--ink)}
.cam-select{width:100%;margin:0 0 6px;padding:6px 10px;border-radius:var(--r-sm);border:1px solid var(--hair-2);
  background:var(--card);color:var(--ink);font-size:12.5px;font-weight:600;outline:none}
.cam-select:disabled{opacity:.65;cursor:default}
.pausebar{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:70;display:none;cursor:pointer;
  background:var(--card);border:1px solid var(--hair-2);color:var(--ink);padding:8px 18px;border-radius:999px;
  font-size:13.5px;font-weight:700;box-shadow:var(--shadow)}
.pausebar.show{display:block;animation:cardIn .2s ease}
</style>
<script>/* 主题引导：无手动选择时跟随系统，须在首屏前定住 data-theme（避免闪屏） */
(function(){try{var t=localStorage.getItem('review2::theme');
  if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';
  document.documentElement.dataset.theme=t;}catch(e){}})();
</script>

</head>
<body class="__BODY_CLASS__">
<aside class="side">
  <div class="menu">
    <button id="btn-auto" title="一键采纳一审建议">采纳<br>一审</button>
    <button id="btn-overview" title="总览目录（可跳转/改判）">总览<br>目录</button>
    <button id="btn-voice" title="语音控制（有本地服务=本机识别）">🎤<br>语音</button>
    <button id="btn-cam" title="手指识别（本地 MediaPipe）">🖐<br>手势</button>
    <button id="btn-import" title="导入判决 JSON">导入<br>判决</button>
    <input type="file" id="import-file" accept=".json" hidden>
    <button id="btn-reset" title="清空本机判决重新审">清空<br>重审</button>
    <button id="btn-theme" title="切换昼夜主题（默认跟随系统）">☾ 夜间</button>
    <span class="spacer" style="flex:1"></span>
    <button id="btn-export" class="primary" title="导出判决 JSON">导出<br>判决</button>
  </div>
</aside>
<div class="col">
<header><div class="wrap">
  <div class="row1">
    <h1>二审判决台 · __BATCH_NAME__</h1>
    __DEMO_TAG__
    <span class="spacer"></span>
    <span class="counts">
      <span id="pos" style="color:var(--ink)"></span>
      <span class="c-keep">留 <b id="c-keep">0</b></span>
      <span class="c-drop">删 <b id="c-drop">0</b></span>
    </span>
  </div>
  <div class="progress">
    <i class="p-keep" id="bar-keep" style="width:0"></i>
    <i class="p-drop" id="bar-drop" style="width:0"></i>
    <i class="p-pending" id="bar-pending" style="width:0"></i>
  </div>
  <div class="demoline">演示批次（历史回放）：这些笔记已处理完毕，本页仅用于体验判决流程；导出的文件交给 Agent 后会在 dry-run 校验时被拦截，不会也无法再删任何东西。</div>
</div></header>
<main>
  <div class="stage" id="stage">
    <article class="swipe-card" id="card" hidden></article>
    <div class="done" id="done">
      <div class="big">🎉</div>
      <h2>全部判完</h2>
      <p id="done-stat"></p>
      <div class="btns">
        <button id="btn-export2" class="primary">导出判决 JSON</button>
        <button id="btn-review">逐张复查 / 改判</button>
      </div>
    </div>
  </div>
  <div class="dock">
    <button class="oval drop" id="btn-drop" title="删（← 或 1，左滑）">✕</button>
    <button class="oval back" id="btn-back" title="撤销上一条（↑ 或 3，上滑）">↺</button>
    <button class="oval keep" id="btn-keep" title="留（→ 或 2，右滑）">✓</button>
  </div>
  <div class="keybar">
    <span class="kb"><kbd class="k-drop">←</kbd>删</span>
    <span class="kb"><kbd class="k-keep">→</kbd>留</span>
    <span class="kb"><kbd>↑</kbd>撤销</span>
    <span class="kb-sep"></span>
    <span class="kb"><kbd class="k-drop">1</kbd>删</span>
    <span class="kb"><kbd class="k-keep">2</kbd>留</span>
    <span class="kb"><kbd>3</kbd>撤销</span>
    <span class="kb-tip">判定后自动跳下一条 · 判决自动存本机</span>
  </div>
</main>
</div>
<div class="cam-panel" id="cam-panel">
  <div class="cam-resize" id="cam-resize" title="拖动缩放预览 · 双击复位"></div>
  <select class="cam-select" id="cam-select" disabled></select>
  <div class="cam-box">
    <video id="cam-video" playsinline muted></video>
    <div class="cam-arr l" id="arr-l">◀</div>
    <div class="cam-arr r" id="arr-r">▶</div>
    <div class="cam-arr u" id="arr-u">▲</div>
    <div class="cam-prog" id="cam-prog"><i></i></div>
    <div id="cam-dbg"></div>
  </div>
  <div class="cam-hint" id="cam-hint">举起一只手：握拳暂停 · 1 指判留 · 2 指判删 · 3 指撤销</div>
</div>
<div class="pausebar" id="pausebar">⏸ 已暂停 · 握拳或点此继续</div>
<div class="vhud" id="vhud" hidden><span class="dot"></span><span id="vhud-txt">语音待命</span></div>
<div class="ov" id="ov" hidden>
  <div class="ov-panel">
    <div class="ov-head">
      <b>总览目录</b>
      <span class="ov-filters" id="ov-filters">
        <button data-f="all" class="on">全部</button>
        <button data-f="pending">待判</button>
        <button data-f="keep">判留</button>
        <button data-f="drop">判删</button>
      </span>
      <button id="ov-close" class="ov-x">关闭</button>
    </div>
    <div class="ov-list" id="ov-list"></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const BATCH = __BATCH_JSON__;
const CAT = {A:"A 工具资源",B:"B 技术实操",C:"C 创作设计",D:"D 搞钱变现",E:"E 学习成长",F:"F 视野观点",G:"G 生活其他"};
const LS_KEY = "review2::" + BATCH.batch;
const N = BATCH.items.length;
let V = load();
let pos = firstPending(0);
let busy = false;
let paused = false;          // 体感「握拳暂停」：暂停时手势/语音/键鼠一律不判决
let lastAutoSig = "";        // 已自动交过的判决指纹（防重复下载）
function setPaused(v){
  paused=!!v;
  const b=document.getElementById('pausebar');
  if(b) b.classList.toggle('show', paused);
  if(paused) toast('已暂停：判决输入全部停下');
}
document.getElementById('pausebar').onclick=()=>{ setPaused(false); toast('已继续'); };

function load(){
  try{ const v = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); return (v && typeof v==="object") ? v : {}; }
  catch(e){ return {}; }
}
function save(){ localStorage.setItem(LS_KEY, JSON.stringify(V)); }
function firstPending(from){
  for(let i=from;i<N;i++){ if(!(BATCH.items[i].id in V)) return i; }
  for(let i=0;i<from;i++){ if(!(BATCH.items[i].id in V)) return i; }
  return N;
}
function counts(){
  let k=0,d=0;
  for(const id in V){ if(V[id]==="keep")k++; else if(V[id]==="drop")d++; }
  return {k,d,p:N-k-d};
}
function toast(msg){
  const t=document.getElementById("toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove("show"),1500);
}

function render(dir){
  { const o=document.getElementById("ov"); if(o && !o.hidden) buildOv(); }
  const {k,d,p}=counts();
  document.getElementById("c-keep").textContent=k;
  document.getElementById("c-drop").textContent=d;
  document.getElementById("bar-keep").style.width=(100*k/N)+"%";
  document.getElementById("bar-drop").style.width=(100*d/N)+"%";
  document.getElementById("bar-pending").style.width=(100*p/N)+"%";
  if(pos>=N || p===0){ showDone(); return; }
  document.getElementById("done").classList.remove("show");
  const card=document.getElementById("card");
  card.hidden=false;
  drawCard(card, BATCH.items[pos]);
  card.classList.remove("fly-drop","fly-keep","back","enter");
  void card.offsetWidth;
  card.classList.add(dir==="back"?"back":"enter");
  card.scrollTop=0;
  document.getElementById("pos").textContent = "第 "+(pos+1)+" / "+N+" 张";
}
function showDone(){
  const card=document.getElementById("card"); card.hidden=true; card.style.transform="";
  const {k,d}=counts();
  document.getElementById("done-stat").textContent="共 "+N+" 篇：判留 "+k+" 篇，判删 "+d+" 篇。可先导出判决，或逐张复查改判。";
  document.getElementById("done").classList.add("show");
  document.getElementById("pos").textContent="完成";
  autoSubmitIfSettled();
}
// 最后一张判完即自动交卷：判决指纹变了才再交一次（撤销后重判会再交，重复渲染不刷屏）
function autoSubmitIfSettled(){
  if(BATCH.demo) return;
  const v=buildVerdict();
  if(v.counts.pending>0) return;
  const sig=v.keep.join(",")+"#"+v.drop.join(",");
  if(sig===lastAutoSig) return;
  lastAutoSig=sig;
  const fname=downloadVerdict(v);
  document.getElementById("done-stat").textContent=
    "共 "+N+" 篇全部判完：判留 "+v.counts.keep+" 篇，判删 "+v.counts.drop+" 篇。"+
    "已自动保存为 "+fname+"，Agent 每 5 分钟检查一次收取路径，收到即自动分析并执行——你不用点任何按钮。"+
    "（若要改判：按 ↑ 返回上一条重判，改完会再自动交一次。）";
  toast("全部判完，判决已自动导出");
}
function el(tag, cls, text){
  const e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e;
}
function drawCard(card, it){
  card.className="swipe-card "+(V[it.id]==="keep"?"card-v-keep":V[it.id]==="drop"?"card-v-drop":"");
  card.style.transform=""; card.scrollTop=0; card.innerHTML="";

  // 盖章
  card.appendChild(el("div","stamp drop","删"));
  card.appendChild(el("div","stamp keep","留"));

  // 元信息行
  const meta=el("div","meta");
  meta.appendChild(el("span","idx","#"+it.idx+" / "+N));
  if(it.cat) meta.appendChild(el("span","cat",CAT[it.cat]||it.cat));
  const t=el("span","title",it.title); t.title=it.title; meta.appendChild(t);
  const now=el("span","now",V[it.id]==="keep"?"已判留 · 右滑维持 / 左滑改删":"已判删 · 左滑维持 / 右滑改留");
  meta.appendChild(now);
  card.appendChild(meta);

  // ① 一审建议
  const map = it.sug==="keep"
    ? {cls:"v-keep", ico:"✓", label:"建议留", sub:"一审"}
    : it.sug==="drop"
    ? {cls:"v-drop", ico:"✕", label:"建议删", sub:"一审"}
    : {cls:"v-dispute", ico:"!", label:"有争议", sub:"一审倾向删"};
  const vd=el("div","verdict "+map.cls);
  vd.appendChild(el("div","v-ico",map.ico));
  const vm=el("div","v-main");
  const vl=el("div","v-label",map.label);
  vl.appendChild(el("small",null,map.sub));
  vm.appendChild(vl);
  vm.appendChild(el("div","v-reason",it.reason));
  vd.appendChild(vm); card.appendChild(vd);

  // ② 笔记总结
  if(it.what || it.use || it.detail || it.cost || it.quote){
    const sm=el("div","summary");
    if(it.what){
      const r=el("div","s-row");
      r.appendChild(el("span","s-tag","讲什么"));
      r.appendChild(el("span","s-txt",it.what)); sm.appendChild(r);
    }
    if(it.use){
      const r=el("div","s-row");
      r.appendChild(el("span","s-tag","有什么用"));
      r.appendChild(el("span","s-txt",it.use)); sm.appendChild(r);
    }
    if(it.next){
      const r=el("div","s-row");
      r.appendChild(el("span","s-tag","下一步"));
      r.appendChild(el("span","s-txt",it.next)); sm.appendChild(r);
    }
    const det=String(it.detail||"").split("‖").map(s=>s.trim()).filter(Boolean);
    if(det.length){
      sm.appendChild(el("div","d-hd","关键细节"));
      const ul=document.createElement("ul"); ul.className="d-list";
      det.forEach(t=>ul.appendChild(el("li",null,t)));
      sm.appendChild(ul);
    }
    if(it.cost){
      const r=el("div","s-row");
      r.appendChild(el("span","s-tag cost","坑/门槛"));
      r.appendChild(el("span","s-txt cost-txt",it.cost)); sm.appendChild(r);
    }
    if(it.quote){
      const q=el("div","quote","「"+it.quote+"」");
      q.appendChild(el("small",null,"原文逐字摘录"+(it.quote_src&&it.quote_src!=="子代理逐字"?"（"+it.quote_src+"）":"")));
      sm.appendChild(q);
    }
    card.appendChild(sm);
  }

  // ③ 全文
  if(it.text){
    const det=el("details","ft");
    det.appendChild(el("summary",null,"展开笔记全文（"+it.text.length+" 字）"));
    const pre=el("pre","fulltext",it.text); det.appendChild(pre);
    card.appendChild(det);
  }
  attachDrag(card);
}

function decide(val){
  if(busy || paused) return;
  const it=BATCH.items[pos];
  const overwriting = V[it.id] && V[it.id]!==val;
  V[it.id]=val; save();
  busy=true;
  const card=document.getElementById("card");
  card.style.transform="";
  void card.offsetWidth;
  card.classList.add(val==="keep"?"fly-keep":"fly-drop");
  const {k,d}=counts();
  document.getElementById("c-keep").textContent=k;
  document.getElementById("c-drop").textContent=d;
  setTimeout(()=>{ busy=false; pos=firstPending(pos+1); render(); },290);
  if(overwriting) toast("已改判"+(val==="keep"?"留":"删"));
}
function back(){
  if(busy || paused) return;
  if(pos>=N){ pos=N-1; delete V[BATCH.items[pos].id]; save(); render("back"); return; }
  if(pos<=0){ toast("已经是第一条了"); return; }
  pos--;
  delete V[BATCH.items[pos].id];
  save();
  render("back");
}

/* ---- 拖拽 ---- */
let drag=null;
function attachDrag(card){ card.addEventListener("pointerdown",onDown); }
function onDown(e){
  if(busy) return;
  if(e.target.closest("button, summary, details, a, input")) return;
  if(e.button!=null && e.button!==0) return;
  const card=document.getElementById("card");
  drag={x:e.clientX,y:e.clientY};
  card.classList.add("grabbing");
  try{ card.setPointerCapture(e.pointerId); }catch(_){}
  card.addEventListener("pointermove",onMove);
  card.addEventListener("pointerup",onUp);
  card.addEventListener("pointercancel",onUp);
}
function onMove(e){
  if(!drag) return;
  const dx=e.clientX-drag.x, dy=e.clientY-drag.y, card=document.getElementById("card");
  card.style.transform="translate("+dx+"px,"+dy+"px) rotate("+(dx/18)+"deg)";
  card.querySelector(".stamp.keep").style.opacity=Math.max(0,Math.min(1,dx/110));
  card.querySelector(".stamp.drop").style.opacity=Math.max(0,Math.min(1,-dx/110));
  document.getElementById("btn-back").classList.toggle("armed", dy<-70 && Math.abs(dy)>Math.abs(dx));
}
function onUp(e){
  if(!drag) return;
  const dx=e.clientX-drag.x, dy=e.clientY-drag.y; drag=null;
  const card=document.getElementById("card");
  card.classList.remove("grabbing");
  document.getElementById("btn-back").classList.remove("armed");
  card.querySelector(".stamp.keep").style.opacity=0;
  card.querySelector(".stamp.drop").style.opacity=0;
  card.removeEventListener("pointermove",onMove);
  card.removeEventListener("pointerup",onUp);
  card.removeEventListener("pointercancel",onUp);
  if(dy<-80 && Math.abs(dy)>Math.abs(dx)*1.1){ back(); }
  else if(dx>110){ decide("keep"); }
  else if(dx<-110){ decide("drop"); }
  else { card.style.transform=""; }
}

document.addEventListener("keydown",e=>{
  if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
  const o=document.getElementById("ov");
  if(e.key==="Escape"){ if(o && !o.hidden) closeOv(); return; }
  if(o && !o.hidden) return;                       // 总览打开时不响应判决键
  if(e.key==="ArrowLeft"||e.key==="1"){ e.preventDefault(); if(pos<N) decide("drop"); }
  else if(e.key==="ArrowRight"||e.key==="2"){ e.preventDefault(); if(pos<N) decide("keep"); }
  else if(e.key==="ArrowUp"||e.key==="3"){ e.preventDefault(); back(); }
});
document.getElementById("btn-drop").onclick=()=>{ if(pos<N) decide("drop"); };
document.getElementById("btn-keep").onclick=()=>{ if(pos<N) decide("keep"); };
document.getElementById("btn-back").onclick=back;

function autoAdopt(){
  const pending=BATCH.items.filter(it=>!(it.id in V));
  if(!pending.length){ toast("没有未判笔记"); return; }
  let k=0,d=0,q=0;
  pending.forEach(it=>{ if(it.sug==="keep")k++; else if(it.sug==="drop")d++; else q++; });
  if(!confirm("将对 "+pending.length+" 篇未判笔记采纳一审建议：判留 "+k+"、判删 "+d+
    (q?"，争议 "+q+" 篇按倾向判删（之后可逐张改判）":"")+"。确定？")) return;
  pending.forEach(it=>{ V[it.id]= it.sug==="keep"?"keep":"drop"; });
  save(); pos=N; render();
}
function buildVerdict(){
  const {k,d,p}=counts(), now=new Date();
  const keep=[],drop=[],pendingIds=[];
  BATCH.items.forEach(it=>{
    if(V[it.id]==="keep")keep.push(it.id);
    else if(V[it.id]==="drop")drop.push(it.id);
    else pendingIds.push(it.id);
  });
  return {
    kind:"second_review_verdict", batch:BATCH.batch, demo:!!BATCH.demo,
    exported_at:now.toISOString(), total:N,
    counts:{keep:k,drop:d,pending:p}, keep, drop, pending:pendingIds
  };
}
function downloadVerdict(v){
  const tag = v.counts.pending>0 ? "draft" : "final";
  const fname="verdict_"+BATCH.batch+"_"+tag+".json";  // 固定名，Agent 守望脚本按名收取
  const blob=new Blob([JSON.stringify(v,null,2)],{type:"application/json"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob); a.download=fname;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),2000);
  return fname;
}
function exportVerdict(){
  const v=buildVerdict();
  if(v.counts.pending>0 && !confirm("还有 "+v.counts.pending+" 篇未判。导出后 Agent 只执行留/删，未判篇不动。继续导出草稿？")) return;
  const tag = v.counts.pending>0 ? "draft" : "final";
  const fname=downloadVerdict(v);
  if(tag==="final") lastAutoSig=v.keep.join(",")+"#"+v.drop.join(",");  // 手点过的这份不再自动重交
  toast(tag==="final" ? "已导出，Agent 会自动收取，你不用做别的" : "已导出草稿 "+fname);
}
function importVerdict(file){
  const r=new FileReader();
  r.onload=()=>{
    try{
      const v=JSON.parse(r.result);
      const ids=new Set(BATCH.items.map(it=>it.id));
      let k=0,d=0,bad=0;
      (v.keep||[]).forEach(id=>{ if(ids.has(id)){V[id]="keep";k++;} else bad++; });
      (v.drop||[]).forEach(id=>{ if(ids.has(id)){V[id]="drop";d++;} else bad++; });
      save(); pos=firstPending(0); render();
      toast("已导入：留 "+k+" / 删 "+d+(bad?" / 非本批次 "+bad:""));
    }catch(err){ alert("文件解析失败："+err.message); }
  };
  r.readAsText(file,"utf-8");
}
document.getElementById("btn-auto").onclick=autoAdopt;
document.getElementById("btn-export").onclick=exportVerdict;
document.getElementById("btn-export2").onclick=exportVerdict;
document.getElementById("btn-import").onclick=()=>document.getElementById("import-file").click();
document.getElementById("import-file").onchange=e=>{ if(e.target.files[0]) importVerdict(e.target.files[0]); e.target.value=""; };
document.getElementById("btn-reset").onclick=()=>{
  if(confirm("清空本机保存的全部判决，重新审？")){ V={}; save(); pos=0; render(); toast("已清空"); }
};
document.getElementById('btn-review').onclick=()=>{ pos=0; render('back'); };

/* ============ 体感控制：手势 / 头动 / 手指 三模（视频不出本机） ============
   手势：手左挥=删 右挥=留 上/下挥=撤；完整滑动（起势→位移→停手）才触发
   头动：头左偏=删 右偏=留 后仰=撤；正视校准后稳定保持 HOLD_MS 才触发
   手指（默认，2026-09-28）：握拳=暂停/继续 · 1指=留 · 2指=删 · 3指=撤销；
        连续 FING_VOTE 帧同一结果才触发，触发后需换手势（或手离开半秒）才能再触发 */
const SWIPE_D=0.18;        // 手势：最小滑动位移（画面宽=1）
const AXIS_R=1.25;         // 手势：主轴须比副轴大这么多倍
const V_START=0.55;        // 手势：起势速度（归一化/秒）
const V_STOP=0.30;         // 手势：停手速度
const SETTLE_MS=150;       // 手势：低速多久判定滑动结束
const TRAJ_MS=900;         // 手势：单条轨迹最长存活
const COOL_MS=400;         // 两次触发最小间隔
const YAW_T=0.30, UP_T=0.07;                     // 头动：左右偏 / 后仰 触发线（钝一点，防轻微偏转误触）
const HOLD_MS=300, NEUTRAL_MS=220, CALIB_N=40;   // 头动：保持 / 回中 / 校准帧数
const FING_VOTE=8;         // 手指：连续多少帧数手指结果一致才判定（约 0.25s）
const FING_COOL=700;       // 手指：两次判定最小间隔
const HAND_GONE_MS=500;    // 手离开画面超过这么久，才允许同一手势再次触发
const CAM_MODE_KEY='review2::cam-mode';
const Cam={on:false,raf:0,stream:null,lm:null,lmMode:null,
  mode:(localStorage.getItem(CAM_MODE_KEY)==='head'?'head':'fingers'),
  armed:true,lastFire:0,lowSince:0,move:null,prev:null,
  flash:null,frames:0,err:null,hand:false,
  cal:[],inited:false,cand:null,neutralAt:0,peak:null,
  baseYaw:0,basePitch:0,smYaw:0,smPitch:0,
  fc:null,noHandAt:0};
let FILESET=null;
const MP_LOCAL = location.protocol !== 'file:';   // file:// 直开时浏览器禁加载本地 wasm，须走本地服务
async function ensureModel(){
  const want=(Cam.mode==='head')?'head':'hand';   // 手指/滑动手势共用 HandLandmarker
  if(Cam.lm && Cam.lmMode===want) return;
  if(Cam.lm){ try{Cam.lm.close();}catch(e){} Cam.lm=null; Cam.lmMode=null; }
  if(!MP_LOCAL){ toast('摄像头需从本地服务打开：双击「启动判决台.bat」'); throw new Error('file protocol'); }
  // 2026-10-10 全本地化：wasm 与模型都在 _vendor/mediapipe/，不再走 jsdelivr / googleapis
  const v=await import('/_vendor/mediapipe/vision_bundle.mjs');
  if(!FILESET) FILESET=await v.FilesetResolver.forVisionTasks('/_vendor/mediapipe');
  if(want==='hand'){
    Cam.lm=await v.HandLandmarker.createFromOptions(FILESET,{
      baseOptions:{modelAssetPath:'/_vendor/mediapipe/hand_landmarker.task'},
      runningMode:'VIDEO',numHands:1});
  }else{
    Cam.lm=await v.FaceLandmarker.createFromOptions(FILESET,{
      baseOptions:{modelAssetPath:'/_vendor/mediapipe/face_landmarker.task'},
      runningMode:'VIDEO',numFaces:1});
  }
  Cam.lmMode=want;
}

const CAM_DEV_KEY='review2::cam-device';
async function startCamStream(id){
  if(Cam.stream){ Cam.stream.getTracks().forEach(t=>t.stop()); Cam.stream=null; }
  const stream=await acquireVideo(id||null);
  Cam.stream=stream;
  const el=document.getElementById('cam-video');
  el.srcObject=stream; await el.play();
  return stream;
}
async function fillCamSelect(){
  const sel=document.getElementById('cam-select');
  let devs=[];
  try{ devs=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput'); }catch(e){}
  const cur=(Cam.stream && Cam.stream.getVideoTracks()[0] &&
    Cam.stream.getVideoTracks()[0].getSettings().deviceId)||'';
  const esc=t=>(''+t).replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));
  let h='<option value="">系统默认（通常为电脑内置）</option>';
  devs.forEach((d,i)=>{
    const lab=d.label||('摄像头 '+(i+1));
    h+='<option value="'+esc(d.deviceId)+'"'+(d.deviceId===cur?' selected':'')+'>'+esc(lab)+'</option>';
  });
  sel.innerHTML=h; sel.disabled=false;
}
const RE_USB=/usb|\u5916\u7f6e|external|\u624b\u673a|phone/i;
const RE_BUILTIN=/integrated|\u5185\u7f6e|embedded|built[\s-]?in/i;
function pickCamDevice(devs, savedId){
  if(savedId && devs.some(d=>d.deviceId===savedId)) return savedId;
  const L=devs.map(d=>d.label||'');
  const hit=re=>devs.find((d,i)=>re.test(L[i]||''));
  let d=hit(RE_BUILTIN);               // 名字带 integrated/内置/embedded
  if(d) return d.deviceId;
  d=devs.find((x,i)=>!RE_USB.test(L[i]||''));  // 再选非USB/手机
  if(d) return d.deviceId;
  return devs.length ? devs[0].deviceId : null;
}
let ACQ_SEQ=0;
function gumWithTimeout(constraints,ms){
  return new Promise((resolve,reject)=>{
    const my=++ACQ_SEQ; let done=false;
    const timer=setTimeout(()=>{ if(!done){done=true;reject(new Error('\u8bbe\u5907\u8fde\u63a5\u8d85\u65f6'));} },ms);
    navigator.mediaDevices.getUserMedia(constraints).then(st=>{
      if(done){ st.getTracks().forEach(t=>t.stop()); return; }
      if(my!==ACQ_SEQ){ done=true;clearTimeout(timer); st.getTracks().forEach(t=>t.stop()); return; }
      done=true;clearTimeout(timer); resolve(st);
    },err=>{ if(!done){done=true;clearTimeout(timer);reject(err);} });
  });
}
async function listCams(){
  try{ return (await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput'); }
  catch(e){ return []; }
}
const VID_OPT={width:{ideal:640},height:{ideal:480}};
async function acquireVideo(preferId){
  let lastErr=null;
  for(let round=0; round<3; round++){
    const devs=await listCams();
    const labeled=devs.filter(d=>d.label);
    const saved=preferId||localStorage.getItem(CAM_DEV_KEY)||null;
    let ids=[];
    if(saved && devs.some(d=>d.deviceId===saved)) ids=[saved];
    else if(labeled.length){
      const want=pickCamDevice(labeled,null);
      ids=labeled.filter(d=>d.deviceId===want || !RE_USB.test(d.label)).map(d=>d.deviceId);
      labeled.forEach(d=>{ if(RE_USB.test(d.label) && !ids.includes(d.deviceId)) ids.push(d.deviceId); });
    } else if(devs.length===1 && devs[0].deviceId) ids=[devs[0].deviceId];
    for(const id of ids){
      try{
        const st=await gumWithTimeout(
          {video:Object.assign({deviceId:{exact:id}},VID_OPT),audio:false},6000);
        if(!localStorage.getItem(CAM_DEV_KEY)) localStorage.setItem(CAM_DEV_KEY,id);
        return st;
      }catch(e){ lastErr=e; }
    }
    // 枚举为空（未授权）：发一次默认请求以触发授权弹窗；超时就作废，下轮枚举到设备名后改道
    try{ return await gumWithTimeout({video:VID_OPT,audio:false}, round===0?7000:4000); }
    catch(e){ lastErr=e; }
  }
  throw lastErr||new Error('\u672a\u627e\u5230\u53ef\u7528\u6444\u50cf\u5934');
}
async function switchCamDevice(id){
  const sel=document.getElementById('cam-select');
  sel.disabled=true;
  localStorage.setItem(CAM_DEV_KEY, id||'');
  try{
    await startCamStream(id||null);
    resetCamState();
    await fillCamSelect();
    setCamHint('已切换摄像头，'+(Cam.mode==='hand'?'举起手继续':'正对镜头继续'));
  }catch(err){
    localStorage.removeItem(CAM_DEV_KEY);
    try{ await startCamStream(null); await fillCamSelect(); resetCamState();
      const cur=Cam.stream.getVideoTracks()[0];
      localStorage.setItem(CAM_DEV_KEY, cur.getSettings().deviceId||'');
    }catch(e){}
    sel.disabled=false;
    toast('该摄像头无法使用（'+(err.name||err.message||'未知')+'），已切回电脑内置');
  }
}
async function toggleCam(){
  if(Cam.on){ stopCam(); return; }
  const btn=document.getElementById('btn-cam');
  btn.textContent='摄像头加载中…'; btn.disabled=true;
  try{
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
      throw new Error('当前浏览器不支持摄像头');
    const savedId=localStorage.getItem(CAM_DEV_KEY)||null;
    await startCamStream(savedId);
    // 保险：若实际流落在USB/手机镜头而机器上有内置，立刻改道
    {
      const devs=await listCams();
      if(devs.some(d=>d.label)){
        const cur=Cam.stream.getVideoTracks()[0].getSettings().deviceId;
        const curLab=(devs.find(d=>d.deviceId===cur)||{}).label||'';
        const want=pickCamDevice(devs,null);
        if(!savedId && RE_USB.test(curLab) && want && want!==cur){
          await startCamStream(want);
          localStorage.setItem(CAM_DEV_KEY,want);
        }
      }
    }
    await ensureModel();
    Cam.on=true;
    resetCamState();
    document.getElementById('cam-panel').classList.add('show');
    await fillCamSelect();           // 已拿到授权，此时设备名完整可见
    btn.textContent='关闭手指识别'; btn.disabled=false; btn.classList.add('on');
    toast(Cam.mode==='head'?'正对镜头校准：左偏删 · 右偏留 · 后仰撤':'举起一只手：握拳暂停 · 1指留 · 2指删 · 3指撤');
    cancelAnimationFrame(Cam.raf);
    Cam.raf=requestAnimationFrame(camLoop);
  }catch(err){
    btn.textContent='🖐 手指识别'; btn.disabled=false;
    if(Cam.stream){ Cam.stream.getTracks().forEach(t=>t.stop()); Cam.stream=null; }
    toast('摄像头不可用（'+(err.name||err.message||'未知')+'），键鼠仍可正常用');
  }
}
function stopCam(){
  Cam.on=false; ACQ_SEQ++; cancelAnimationFrame(Cam.raf);
  if(Cam.stream) Cam.stream.getTracks().forEach(t=>t.stop());
  if(Cam.lm){ try{Cam.lm.close();}catch(e){} }
  Cam.stream=null; Cam.lm=null;
  const pnl=document.getElementById('cam-panel'); if(pnl) pnl.classList.remove('show');
  const btn=document.getElementById('btn-cam');
  if(btn){ btn.textContent='🖐 手指识别'; btn.disabled=false; btn.classList.remove('on'); }
}
function resetCamState(){
  Cam.armed=true; Cam.lastFire=0; Cam.lowSince=0; Cam.move=null; Cam.prev=null;
  Cam.flash=null; Cam.frames=0; Cam.err=null; Cam.hand=false; Cam._hk=null;
  Cam.cal=[]; Cam.inited=false; Cam.cand=null; Cam.neutralAt=0; Cam.peak=null;
  Cam.baseYaw=0; Cam.basePitch=0; Cam.smYaw=0; Cam.smPitch=0;
  Cam.fc=null; Cam.noHandAt=0;
}
function camLoop(){
  if(!Cam.on) return;
  Cam.frames=(Cam.frames||0)+1;
  try{
    const video=document.getElementById('cam-video');
    if(video.readyState>=2){
      const r=Cam.lm.detectForVideo(video, performance.now());
      if(Cam.mode==='head'){
        const face=(r.faceLandmarks && r.faceLandmarks.length)?r.faceLandmarks[0]:null;
        if(face) consumeFace(face); else noFace();
      }else{
        // tasks-vision HandLandmarker 结果字段是 landmarks
        const hand=(r.landmarks && r.landmarks.length)?r.landmarks[0]:null;
        if(hand){
          Cam.hand=true; Cam.noHandAt=0;
          if(Cam.mode==='fingers') consumeHand(hand, performance.now());
          else { const q=hand[9]; feedPoint(1-q.x, q.y, performance.now()); }
        }else noHand(performance.now());
      }
    }
  }catch(e){
    Cam.err=String(e&&e.message||e);
    setCamHint('识别异常：'+Cam.err.slice(0,40));
  }
  Cam.raf=requestAnimationFrame(camLoop);
}
/* 滑动状态机（纯坐标输入，便于测试）：
   静止 → 速度超 V_START 起一条轨迹 → 低速 SETTLE_MS 毫秒或超时结算
   位移≥SWIPE_D 且主轴明确才触发；触发后停手 SETTLE_MS 毫秒即重新上膛，两次挥手间隔≥COOL_MS */
function feedPoint(x,y,now){
  const prev=Cam.prev;
  const dt=prev? Math.max(8,now-prev.lastT)/1000 : 0;
  const vx=prev? (x-prev.x)/dt : 0;
  const vy=prev? (y-prev.y)/dt : 0;
  const sp=Math.hypot(vx,vy);
  Cam.prev={x,y,lastT:now};

  let live=null, prog=0;
  if(Cam.flash && now>Cam.flash.until) Cam.flash=null;

  // 停手计时（按真实毫秒，fps 无关）
  if(sp<V_STOP) Cam.lowSince = Cam.lowSince||now;
  else Cam.lowSince=0;

  if(!Cam.armed){
    if(Cam.lowSince && now-Cam.lowSince>=SETTLE_MS){ Cam.armed=true; Cam.move=null; }
  }
  if(Cam.armed && now-Cam.lastFire>COOL_MS){
    const m=Cam.move;
    if(!m){
      if(sp>V_START) Cam.move={t0:now,x0:x,y0:y,lowSince:0};
    }else{
      const dx=x-m.x0, dy=y-m.y0, dist=Math.hypot(dx,dy);
      const adx=Math.abs(dx), ady=Math.abs(dy);
      if(adx>=ady) live= dx>0?'right':'left';
      else if(ady>0.02) live='up';
      prog=Math.min(1,dist/SWIPE_D);
      if(sp<V_STOP) m.lowSince=m.lowSince||now; else m.lowSince=0;
      const settled=m.lowSince && now-m.lowSince>=SETTLE_MS;
      const timeout=now-m.t0>TRAJ_MS;
      if(settled||timeout){
        let dir=null;
        if(dist>=SWIPE_D){
          if(adx>=ady*AXIS_R) dir=dx>0?'right':'left';
          else if(ady>=adx*AXIS_R) dir='up';
        }
        if(dir){ fireGesture(dir,now); }
        Cam.move=null; live=null; prog=0;
      }
    }
  }
  const shown=(Cam.flash&&Cam.flash.dir)||live;
  setHud(shown, Cam.flash?1:prog);
  drawHandDbg(sp, Cam.move, x, y);
  if(!Cam.flash && !Cam.move) hintOnce('seen','✋ 看到手了：左挥删 · 右挥留 · 上下挥撤');
}
function hintOnce(key,text){ if(Cam._hk!==key){ Cam._hk=key; setCamHint(text); } }
function noHand(now){
  now=now||performance.now();
  Cam.hand=false; Cam.move=null; Cam.prev=null; Cam.lowSince=0;
  if(!Cam.noHandAt) Cam.noHandAt=now;
  if(now-Cam.noHandAt>HAND_GONE_MS) Cam.fc=null;   // 手离开够久才允许同一手势再触发
  setHud(Cam.flash?Cam.flash.dir:null, Cam.flash?1:0);
  const d=document.getElementById('cam-dbg');
  if(d) d.innerHTML='<span style="opacity:.75">没看到手 — 把手举进画面中央</span>';
  if(Cam.mode==='fingers'){
    if(!Cam.flash) hintOnce('nohand2','没看到手：举起一只手（握拳暂停 · 1指留 · 2指删 · 3指撤）');
  }else if(!Cam.flash) hintOnce('nohand','没看到手：把手举进画面（左挥删 · 右挥留 · 上下挥撤）');
}
function fireGesture(dir,now){
  now=now||performance.now();
  Cam.armed=false; Cam.lowSince=0; Cam.lastFire=now; Cam._hk='fire';
  Cam.flash={dir,until:now+420};
  if(dir==='left'){ decide('drop'); setCamHint('◀ 已判删'); }
  else if(dir==='right'){ decide('keep'); setCamHint('已判留 ▶'); }
  else { back(); setCamHint('▲ 已撤销，返回上一条'); }
}
function setHud(dir,prog){
  const map={l:'left',r:'right',u:'up'};
  for(const d of ['l','u','r']){
    document.getElementById('arr-'+d).classList.toggle('hot', dir===map[d]);
  }
  const bar=document.getElementById('cam-prog');
  bar.style.display = (dir&&prog>0.05) ? 'block' : 'none';
  bar.querySelector('i').style.width = Math.round((prog||0)*100)+'%';
}
function drawHandDbg(sp,m,x,y){
  const el=document.getElementById('cam-dbg');
  if(!el) return;
  const dist=m?Math.hypot(x-m.x0,y-m.y0):0;
  el.innerHTML='✋ '+(m?'滑动中 ':'就绪 ')
    +'速度'+sp.toFixed(2)+' 位移'+dist.toFixed(2)
    +'<small>掌心('+x.toFixed(2)+','+y.toFixed(2)+') 触发需位移 0.18 且方向明确，停手生效</small>';
}
/* ---------- 手指识别（握拳=暂停 · 1指=留 · 2指=删 · 3指=撤销） ---------- */
/* 伸展判定：指尖离腕比指中节离腕远 → 该指伸直（不数拇指，拇指姿态太飘） */
function countExtended(lm){
  const w=lm[0];
  const d=i=>Math.hypot(lm[i].x-w.x, lm[i].y-w.y);
  let n=0;
  [[8,6],[12,10],[16,14],[20,18]].forEach(p=>{ if(d(p[0])>d(p[1])*1.15) n++; });
  return n;
}
function consumeHand(lm,now){
  if(!Cam.fc) Cam.fc={count:-1,run:0,fired:false};
  const c=countExtended(lm);
  if(c===Cam.fc.count) Cam.fc.run++;
  else { Cam.fc.count=c; Cam.fc.run=1; Cam.fc.fired=false; }
  const stable=Cam.fc.run>=FING_VOTE;
  if(stable && !Cam.fc.fired && now-Cam.lastFire>FING_COOL){
    if(c===0){                                        // 握拳：暂停 / 继续（切换）
      Cam.fc.fired=true; Cam.lastFire=now;
      setPaused(!paused);
      setCamHint(paused?'⏸ 已暂停（再握拳继续）':'▶ 已继续');
    }else if(!paused && c>=1 && c<=3){
      Cam.fc.fired=true; Cam.lastFire=now;
      if(c===1){ decide('keep'); setCamHint('☝ 1 指 → 已判留'); }
      else if(c===2){ decide('drop'); setCamHint('✌ 2 指 → 已判删'); }
      else { back(); setCamHint('🤟 3 指 → 已撤销，返回上一条'); }
    }
  }
  drawFingerDbg(c);
  if(!paused && !Cam.flash) hintOnce('seen2','🖐 看到手了：握拳暂停 · 1指留 · 2指删 · 3指撤');
}
function drawFingerDbg(c){
  const el=document.getElementById('cam-dbg'); if(!el) return;
  const fc=Cam.fc||{count:-1,run:0};
  const label=['✊ 握拳（暂停/继续）','☝ 1 指（留）','✌ 2 指（删）','🤟 3 指（撤销）','🖖 4 指（不用）'][Math.min(c,4)];
  el.innerHTML=(paused?'⏸ 已暂停 · ':'🖐 ')+label
    +'<small>稳定 '+Math.min(fc.run,FING_VOTE)+'/'+FING_VOTE+'（连续一致才触发，防误判）</small>';
}
/* ---------- 头动识别 ---------- */
function median(a){ const b=a.slice().sort((x,y)=>x-y); return b[Math.floor(b.length/2)]; }
function consumeFace(p){
  const X=q=>1-q[0];                        // 镜像，与用户自身左右一致
  const eL=p[33], eR=p[263], nose=p[1], chin=p[152];
  const ex=(X(eL)+X(eR))/2, ey=(eL[1]+eR[1])/2;
  const iod=Math.abs(X(eL)-X(eR))||1e-6;
  const yawRaw=(X(nose)-ex)/iod;
  const pitchRaw=(nose[1]-ey)/((chin[1]-ey)||1e-6);  // 后仰→变小
  if(!Cam.inited){ Cam.smYaw=yawRaw; Cam.smPitch=pitchRaw; Cam.inited=true; }
  else{ Cam.smYaw=Cam.smYaw*.5+yawRaw*.5; Cam.smPitch=Cam.smPitch*.55+pitchRaw*.45; }
  if(Cam.cal.length<CALIB_N){
    Cam.cal.push([yawRaw,pitchRaw]);
    setCamHint('请正视镜头，校准…'+Math.round(100*Cam.cal.length/CALIB_N)+'%');
    setHud(null,0); drawHeadDbg(0,0,true);
    if(Cam.cal.length===CALIB_N){
      Cam.baseYaw=median(Cam.cal.map(a=>a[0]));
      Cam.basePitch=median(Cam.cal.map(a=>a[1]));
      Cam.peak={l:0,r:0,u:0};
      setCamHint('校准好啦：左偏删 · 右偏留 · 后仰撤');
    }
    return;
  }
  evalHead(Cam.smYaw-Cam.baseYaw, Cam.basePitch-Cam.smPitch);
}
function noFace(){
  Cam.cand=null; Cam.neutralAt=0;
  setHud(Cam.flash?Cam.flash.dir:null, Cam.flash?1:0);
  const d=document.getElementById('cam-dbg');
  if(d) d.innerHTML='<span style="opacity:.75">没看到脸 — 正对镜头</span>';
  if(!Cam.flash) hintOnce('noface','没看到脸：正对镜头（左偏删 · 右偏留 · 后仰撤）');
}
function evalHead(yaw,up){
  const now=performance.now();
  let dir=null;
  if(up>UP_T && Math.abs(yaw)<YAW_T*0.8) dir='up';
  else if(yaw>YAW_T) dir='right';
  else if(yaw<-YAW_T) dir='left';
  const neutral=Math.abs(yaw)<YAW_T*0.45 && up<UP_T*0.5;
  if(!Cam.armed){
    if(neutral){ if(!Cam.neutralAt) Cam.neutralAt=now;
      if(now-Cam.neutralAt>=NEUTRAL_MS){ Cam.armed=true; Cam.cand=null; } }
    else Cam.neutralAt=0;
  }
  let prog=0;
  if(Cam.armed && dir && now-Cam.lastFire>COOL_MS){
    if(Cam.cand && Cam.cand.dir===dir) prog=Math.min(1,(now-Cam.cand.t)/HOLD_MS);
    else { Cam.cand={dir,t:now}; prog=0; }
    if(prog>=1){ fireGesture(dir,now); Cam.cand=null; prog=0; }
  }else if(!dir){ Cam.cand=null; }
  if(Cam.peak){
    if(yaw<0) Cam.peak.l=Math.max(Cam.peak.l,-yaw); else Cam.peak.r=Math.max(Cam.peak.r,yaw);
    Cam.peak.u=Math.max(Cam.peak.u,up);
  }
  setHud(dir,prog);
  drawHeadDbg(yaw,up);
  if(!dir && now-Cam.lastFire>1500) hintOnce('seenface','🙂 看到脸了：左偏删 · 右偏留 · 后仰撤');
}
function drawHeadDbg(yaw,up,calib){
  const el=document.getElementById('cam-dbg'); if(!el) return;
  if(calib){ el.innerHTML='🙂 校准中 '+Cam.cal.length+'/'+CALIB_N+' 请正视'; return; }
  const f=x=>(x>=0?'+':'')+x.toFixed(3);
  const p=Cam.peak||{l:0,r:0,u:0};
  el.innerHTML='🙂 偏 '+f(yaw)+' ／ 仰 '+f(up)
    +'<small>峰值 左'+p.l.toFixed(3)+' 右'+p.r.toFixed(3)+' 仰'+p.u.toFixed(3)+'（触发线 '+YAW_T+' / '+UP_T+'）</small>';
}
/* ---------- 模式切换 ---------- */
async function setMode(m){
  if(m==='hand'||m==='head'){ Cam.mode=m; localStorage.setItem(CAM_MODE_KEY,m); }
  updateModeUI();
  if(Cam.on){
    try{ await ensureModel(); resetCamState();
      toast(Cam.mode==='hand'?'已切换：手势控制':'已切换：头动控制'); }
    catch(e){ toast('模型加载失败：'+((e&&e.message)||e)); }
  }
}
function updateModeUI(){
  const mh=document.getElementById('m-hand'), md=document.getElementById('m-head');
  if(mh) mh.classList.toggle('on', Cam.mode==='hand');
  if(md) md.classList.toggle('on', Cam.mode==='head');
  const h=document.getElementById('cam-hint');
  if(h && !Cam.flash) h.textContent = Cam.mode==='head'
    ? '正对镜头：左偏删 · 右偏留 · 后仰撤'
    : '举起一只手：握拳暂停 · 1指留 · 2指删 · 3指撤';
}
function setCamHint(t){ const h=document.getElementById('cam-hint'); if(h) h.textContent=t; }
/* 手指识别面板：点「🖐 手指识别」开关（手势滑动/头动代码保留，未接线） */
/* 预览窗大小：拖左上角把手自由缩放，双击复位；尺寸记本机 */
const CAM_W_KEY='review2::cam-width', CAM_W_DEF=178;
function applyCamWidth(w){
  w=Math.max(140,Math.min(560,Math.round(w||CAM_W_DEF)));
  document.getElementById('cam-panel').style.width=w+'px';
  return w;
}
(function initCamResize(){
  const panel=document.getElementById('cam-panel');
  const h=document.getElementById('cam-resize');
  if(!panel||!h) return;                        // 体感面板未启用时跳过
  applyCamWidth(parseInt(localStorage.getItem(CAM_W_KEY)||CAM_W_DEF,10));
  let sx=0, sw=0, dragging=false;
  h.addEventListener('pointerdown',e=>{
    dragging=true; sx=e.clientX; sw=panel.getBoundingClientRect().width;
    try{h.setPointerCapture(e.pointerId);}catch(_){}
    e.preventDefault(); e.stopPropagation();
  });
  h.addEventListener('pointermove',e=>{
    if(!dragging) return;
    applyCamWidth(sw-(e.clientX-sx));   // 面板右贴边：向左拖=变大
    e.preventDefault();
  });
  const stop=()=>{ if(!dragging) return; dragging=false;
    localStorage.setItem(CAM_W_KEY, String(parseInt(panel.style.width,10)||CAM_W_DEF)); };
  h.addEventListener('pointerup',stop);
  h.addEventListener('pointercancel',stop);
  h.addEventListener('dblclick',()=>{
    applyCamWidth(CAM_W_DEF); localStorage.setItem(CAM_W_KEY,String(CAM_W_DEF));
  });
})();
window.addEventListener('beforeunload', stopCam);
document.getElementById('btn-cam').onclick=toggleCam;
window.__camTest={
  reset:resetCamState,
  feed:(pts)=>{ const t0=performance.now();
    pts.forEach((p,i)=>feedPoint(p[0],p[1],t0+i*32)); },  // 每点32ms≈30fps
  evalHead:(y,u)=>evalHead(y,u),
  median, fire:fireGesture,
  setMode:(m)=>{ Cam.mode=m; },
  count:(lm)=>countExtended(lm),
  feedHand:(lm,ago)=>consumeHand(lm, performance.now()-(ago||0)),
  setPaused:(v)=>setPaused(v),
  state:()=>({mode:Cam.mode,armed:Cam.armed,move:!!Cam.move,cand:Cam.cand,
    paused,busy,pos,keep:counts().k,drop:counts().d,
    fc:Cam.fc?Object.assign({},Cam.fc):null})};

/* ---------- 总览目录（点哪改哪） ---------- */
let ovFilter='all';
function buildOv(){
  const list=document.getElementById('ov-list'); if(!list) return;
  list.innerHTML='';
  let shown=0;
  BATCH.items.forEach((it,i)=>{
    const v=V[it.id];
    if(ovFilter==='pending'&&v) return;
    if(ovFilter==='keep'&&v!=='keep') return;
    if(ovFilter==='drop'&&v!=='drop') return;
    shown++;
    const row=el('button','ov-row'+(i===pos?' cur':''));
    row.appendChild(el('span','ov-idx','#'+it.idx));
    row.appendChild(el('span','ov-badge '+(v==='keep'?'keep':v==='drop'?'drop':'pending'),
      v==='keep'?'留':v==='drop'?'删':'待判'));
    const t=el('span','ov-title',it.title); t.title=it.title; row.appendChild(t);
    row.onclick=()=>goto(i);
    list.appendChild(row);
  });
  if(!shown) list.appendChild(el('div','ov-empty','（此筛选下没有记录）'));
}
function syncOvFilter(){
  document.querySelectorAll('#ov-filters button').forEach(b=>b.classList.toggle('on', b.dataset.f===ovFilter));
}
function openOv(){ const o=document.getElementById('ov'); if(!o) return; ovFilter='all'; syncOvFilter(); buildOv(); o.hidden=false; }
function closeOv(){ const o=document.getElementById('ov'); if(o) o.hidden=true; }
function goto(i){ pos=i; closeOv(); render('jump'); }
document.getElementById('btn-overview').onclick=openOv;
document.getElementById('ov-close').onclick=closeOv;
document.getElementById('ov').addEventListener('click',e=>{ if(e.target.id==='ov') closeOv(); });
document.querySelectorAll('#ov-filters button').forEach(b=> b.onclick=()=>{
  ovFilter=b.dataset.f; syncOvFilter(); buildOv();
});

/* ---------- 语音控制（Chrome Web Speech API） ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec=null, voiceOn=false, voiceLast=0, voiceRestart=null;
function parseVoice(t){
  t=(t||'').replace(/[\s。，,\.、！!？?~～]/g,'');
  if(!t) return null;
  // 最后出现者优先：一个识别窗口里可能同时残留上一条指令（"删除保留"＝先删后留，当前意图是留）。
  // 老实现按 撤销→删→留 的固定顺序判，窗口残留会让旧指令抢跑——2026-10-10 真机复现后改为比位置。
  const PATS=[['back',/撤销|撤回|退回|上一个|上一张|返回|取消|作废/],
              ['drop',/删|丢掉|丢弃|不要|去掉|去除/],
              ['keep',/留|保留|留下|收下|要了|通过/]];
  let best=null, bi=-1;
  for(const p of PATS){
    const m=t.match(p[1]);
    if(m){ const i=t.lastIndexOf(m[0]); if(i>bi){ bi=i; best=p[0]; } }
  }
  return best;
}
function vhud(show,txt,on){
  const h=document.getElementById('vhud'); if(!h) return;
  h.hidden=!show; h.classList.toggle('on',!!on);
  if(txt!=null) document.getElementById('vhud-txt').textContent=txt;
}
/* ---------- 语音控制：双引擎 ----------
   本地引擎（优先）：浏览器采麦克风 PCM → POST 本地服务 /asr/transcribe → sherpa 小模型
     识别全在本机，零网络延迟。只在“启动判决台.bat”起的服务下可用。
   浏览器引擎（兜底）：Chrome Web Speech API，走 Google 服务端，国内慢/抽风。
   两个引擎共用 parseVoice 与相同的开火守卫。 */
let VOICE_ENGINE=null;   // 'local' | 'web'
const LOCAL={ctx:null,src:null,proc:null,mute:null,stream:null,
  ring:new Int16Array(16000*2),w:0,filled:0,timer:0,consumed:0};

function voiceFire(v,from){
  const now=performance.now(); if(now-voiceLast<500) return;
  const o=document.getElementById('ov'); if(o && !o.hidden) return;
  voiceLast=now;
  vhud(true,'执行 · '+(v==='keep'?'保留':v==='drop'?'删除':'撤销')+'（'+from+'）',true);
  if(v==='back') back(); else if(pos<N) decide(v);
}
async function probeLocal(){
  try{
    const ctrl=new AbortController(); const t=setTimeout(()=>ctrl.abort(),1500);
    const r=await fetch('/asr/ping',{signal:ctrl.signal}); clearTimeout(t);
    if(!r.ok) return false;
    const j=await r.json(); return !!j.ok;
  }catch(e){ return false; }
}
/* —— 本地引擎 —— */
let LOCAL_SIG='';        // 兼容旧字段（不再使用）
let LOCAL_SILENT=0;      // 连续空文本轮数（诊断麦克风/自动播放）
let LOCAL_LASTCMD=null;  // 窗口里“最后一条指令”→只有它变化才开火（一句话一次，连说不漏）
async function localStart(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
  LOCAL.stream=stream;
  const ctx=new (window.AudioContext||window.webkitAudioContext)({sampleRate:16000});
  LOCAL.ctx=ctx;
  if(ctx.state==='suspended'){ try{ await ctx.resume(); }catch(e){} }   // 自动播放策略兜底
  LOCAL.src=ctx.createMediaStreamSource(stream);
  LOCAL.proc=ctx.createScriptProcessor(4096,1,1);
  LOCAL.mute=ctx.createGain(); LOCAL.mute.gain.value=0;   // 拉数据但不外放（防回声）
  const ring=LOCAL.ring;
  LOCAL.proc.onaudioprocess=e=>{
    const inp=e.inputBuffer.getChannelData(0);
    for(let i=0;i<inp.length;i++){
      const v=inp[i]<-1?-1:(inp[i]>1?1:inp[i]);
      ring[LOCAL.w]=v*32767; LOCAL.w=(LOCAL.w+1)%ring.length;
      if(LOCAL.filled<ring.length) LOCAL.filled++;
    }
  };
  LOCAL.src.connect(LOCAL.proc); LOCAL.proc.connect(LOCAL.mute); LOCAL.mute.connect(ctx.destination);
  LOCAL.consumed=0; LOCAL_SIG=''; LOCAL_SILENT=0; LOCAL_LASTCMD=null;
  LOCAL.timer=setInterval(localPoll,450);
  vhud(true,'本地语音待命…正在听（sherpa 本机识别）',false);
}
async function localPoll(){
  const n=LOCAL.filled; if(n<16000*0.6) return;                 // 至少攒 0.6s
  const ring=LOCAL.ring,w=LOCAL.w,buf=new Int16Array(n);
  for(let i=0;i<n;i++) buf[i]=ring[(w-n+i+ring.length*2)%ring.length];
  try{
    const r=await fetch('/asr/transcribe',{method:'POST',body:buf.buffer,headers:{'Content-Type':'application/octet-stream'}});
    const j=await r.json();
    if(j.err){ vhud(true,'本地识别出错：'+String(j.err).slice(0,30),false); return; }
    const t=(j.text||'').replace(/\s+/g,'');
    if(!t){ LOCAL_SILENT++; if(LOCAL_SILENT===12) vhud(true,'本地待命中…没听到声音（检查麦克风）',false); return; }
    LOCAL_SILENT=0;
    // 2026-10-10 修（真机复现）：去重不能按文本长度/内容——滑动窗口会让同一句话
    // 溅射出不同文本（“删除保留”→残留“删除保留”→滑成“保留”），按内容比对各触发一次。
    // 改为跟踪“窗口里最后一条指令”：它不变不开火，它变了才开火；窗口里没指令时清零。
    // 效果：说一句判一次；快速连说“删删删留”也一条不落。
    const v=parseVoice(t);
    if(v && v!==LOCAL_LASTCMD){ LOCAL_LASTCMD=v; voiceFire(v,'本地'); }
    else{ if(!v) LOCAL_LASTCMD=null; vhud(true,'本地听到「'+t.slice(-10)+'」',true); }
  }catch(e){ /* 一次抖动不管，下轮再来 */ }
}
function localStop(){
  clearInterval(LOCAL.timer); LOCAL.timer=0;
  try{ LOCAL.proc&&LOCAL.proc.disconnect(); LOCAL.src&&LOCAL.src.disconnect();
       LOCAL.mute&&LOCAL.mute.disconnect(); LOCAL.ctx&&LOCAL.ctx.close(); }catch(e){}
  if(LOCAL.stream){ LOCAL.stream.getTracks().forEach(t=>t.stop()); LOCAL.stream=null; }
  LOCAL.filled=0; LOCAL.w=0;
}
/* —— 统一开关：优先本地，探不到再回落浏览器引擎 —— */
async function voiceStart(){
  if(voiceOn) return;
  if(await probeLocal()){
    VOICE_ENGINE='local';
    voiceOn=true; localStorage.setItem('review2::voice','local');
    try{ await localStart(); }
    catch(e){ toast('麦克风打开失败：'+String(e.message||e).slice(0,60)); voiceOn=false; localStop(); return; }
    const btn=document.getElementById('btn-voice'); if(btn) btn.classList.add('on');
    toast('语音已开启 · 本机识别（说「保留/删除/撤销」）');
    return;
  }
  if(!SR){ toast('本地语音服务未启动，且此浏览器不支持网页语音（建议 Chrome）'); return; }
  VOICE_ENGINE='web';
  voiceOn=true; localStorage.setItem('review2::voice','web');
  buildRec();
  try{ rec.start(); }catch(e){}
  const btn=document.getElementById('btn-voice'); if(btn){ btn.classList.add('on'); }
  vhud(true,'网页语音待命…正在听（走 Google，国内可能不稳）',false);
  toast('语音已开启 · 网页识别（本地服务未启动；启动判决台.bat 可切换本机识别）');
}
function voiceStop(){
  voiceOn=false; localStorage.removeItem('review2::voice');
  localStop();
  clearTimeout(voiceRestart);
  if(rec){ try{ rec.stop(); }catch(e){} }
  const btn=document.getElementById('btn-voice'); if(btn){ btn.classList.remove('on'); }
  vhud(false);
  toast('语音已关闭');
}
function voiceToggle(){ voiceOn?voiceStop():voiceStart(); }
document.getElementById('btn-voice').onclick=voiceToggle;
/* —— 浏览器引擎（兜底）：Chrome Web Speech API，走 Google 服务端 —— */
function buildRec(){
  rec=new SR();
  rec.lang='zh-CN'; rec.continuous=true;
  // 2026-10-10 提速：开中间结果＋指令早发——说完“删”的瞬间开火，不等引擎结案；
  // consumed 记录已消费的识别文本长度，防止同一句在 interim/final 各触发一次。
  rec.interimResults=true; rec.maxAlternatives=1;
  let WEB_LASTCMD=null;   // 同本地引擎：最后一条指令变化才开火
  rec.onresult=e=>{
    let fin='', interim='';
    for(let i=e.resultIndex;i<e.results.length;i++){
      if(e.results[i].isFinal) fin+=e.results[i][0].transcript;
      else interim+=e.results[i][0].transcript;
    }
    const buf=(fin+interim);
    const v=parseVoice(buf);
    if(v && v!==WEB_LASTCMD){ WEB_LASTCMD=v; voiceFire(v,'网页'); }
    else{ if(!v) WEB_LASTCMD=null; vhud(true,'听到「'+buf.trim().slice(-10)+'」',true); }
  };
  rec.onerror=e=>{
    const m=e.error;
    if(m==='no-speech'||m==='aborted') return;
    if(m==='not-allowed'||m==='service-not-allowed'){ toast('麦克风未授权，语音已关'); voiceStop(); return; }
    if(m==='network'){ toast('语音服务连不上（国内网络常被墙）—可继续用键鼠'); }
    else toast('语音出错：'+m);
  };
  // 断句重连提速：400ms→220ms（国内网络下 onend 频繁，重连越快断档感越小）
  rec.onend=()=>{ if(voiceOn){ WEB_LASTCMD=null; voiceRestart=setTimeout(()=>{ try{rec.start();}catch(e){} },220); } };
}

/* ---------- 昼夜主题切换（默认跟随系统，手动一次后记住选择） ---------- */
(function(){
  var K='review2::theme', b=document.getElementById('btn-theme');
  var paint=function(){ if(b) b.textContent = document.documentElement.dataset.theme==='light' ? '☀︎ 白天' : '☾ 夜间'; };
  if(b) b.onclick=function(){
    var next = document.documentElement.dataset.theme==='light' ? 'dark' : 'light';
    document.documentElement.dataset.theme=next;
    try{ localStorage.setItem(K,next); }catch(e){}
    paint();
  };
  paint();
})();

updateModeUI();
render();
</script>
</body>
</html>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--batch", default=None)
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    inp = args.input if os.path.isabs(args.input) else os.path.join(BASE_DIR, args.input)
    out = args.output if os.path.isabs(args.output) else os.path.join(BASE_DIR, args.output)
    batch = args.batch or os.path.splitext(os.path.basename(inp))[0].replace("review_batch_", "")

    items, bad = [], 0
    with open(inp, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            nid = (row.get("id") or "").strip()
            if not nid:
                continue
            if len(nid) != 24 or any(c not in "0123456789abcdef" for c in nid):
                bad += 1
            text = ""
            fp = (row.get("fulltext") or "").strip()
            if fp and fp != "-":
                p = fp if os.path.isabs(fp) else os.path.join(BASE_DIR, fp)
                if os.path.exists(p):
                    text = open(p, encoding="utf-8").read()[:TEXT_LIMIT]
            items.append({
                "idx": len(items) + 1,
                "id": nid,
                "title": (row.get("title") or "").strip(),
                "cat": (row.get("category") or "").strip(),
                "sug": (row.get("suggestion") or "drop").strip(),
                "reason": (row.get("reason") or "").strip(),
                "what": (row.get("what") or "").strip(),
                "use": (row.get("use") or "").strip(),
                "next": (row.get("next") or "").strip(),
                "detail": (row.get("detail") or "").strip(),
                "cost": (row.get("cost") or "").strip(),
                "quote": (row.get("quote") or "").strip(),
                "quote_src": (row.get("quote_src") or "").strip(),
                "text": text,
            })
    if bad:
        print("警告: %d 个 ID 不是 24 位 hex，请检查 TSV" % bad, file=sys.stderr)

    payload = {
        "batch": batch,
        "demo": bool(args.demo),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (TEMPLATE
            .replace("__BATCH_NAME__", batch)
            .replace("__BODY_CLASS__", "demo" if args.demo else "")
            .replace("__DEMO_TAG__", '<span class="demotag">演示 · 历史回放</span>' if args.demo else "")
            .replace("__BATCH_JSON__", data_json))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK: %d 篇 -> %s (%.1f KB)" % (len(items), out, os.path.getsize(out) / 1024))

if __name__ == "__main__":
    main()
