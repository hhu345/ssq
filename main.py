# -*- coding: utf-8 -*-
"""
双色球综合选号 - 手机版 (Kivy)
整合分析 · 选号 · 回测 · 购彩记录
"""

import os
import sys
import json
import random
import re
import uuid
import threading
import io
from collections import Counter
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock, mainthread
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import get_color_from_hex
from kivy.core.window import Window

Window.clearcolor = (0.96, 0.96, 0.96, 1)

# matplotlib for charts (Agg = no display needed)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'WenQuanYi Micro Hei']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================
# 核心常量
# ============================================================
RED_COUNT = 33
BLUE_COUNT = 16
RED_PICK = 6

W_FREQ = 0.30
W_OMIT = 0.35
W_TAIL = 0.20
W_ZONE = 0.15

SUM_RANGE = (90, 120)
ODD_RANGE = (2, 4)
BIG_RANGE = (2, 4)
SPAN_RANGE = (15, 30)
MAX_CONSEC = 3
ZONE_MAX_IN_ONE = 4

PRIZE_NAMES = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "四等奖", 5: "五等奖", 6: "六等奖"}
PRIZE_AMOUNT = {1: 5000000, 2: 150000, 3: 3000, 4: 200, 5: 10, 6: 5}

DATA_URL = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"

RED = get_color_from_hex("#E74C3C")
RED_LIGHT = get_color_from_hex("#FADBD8")
BLUE = get_color_from_hex("#3498DB")
BLUE_LIGHT = get_color_from_hex("#D6EAF8")
ACCENT = get_color_from_hex("#2ECC71")
DARK = get_color_from_hex("#2C3E50")
GRAY = get_color_from_hex("#95A5A6")
WHITE = get_color_from_hex("#FFFFFF")

# ============================================================
# 工具函数
# ============================================================

def today_str():
    return datetime.now().strftime('%Y-%m-%d')


def _to_int(v):
    if v is None: return 0
    m = re.search(r'\d+', str(v))
    return int(m.group()) if m else 0


def norm(d):
    mx = max(d.values()) if d else 1
    return {k: v / mx for k, v in d.items()}


def fmt_nums(nums):
    return " ".join(f"{x:02d}" for x in nums)


# ============================================================
# 数据层
# ============================================================

class DataManager:
    """数据获取 + 缓存 + 记录管理"""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "ssq_history.json"
        self.records_file = self.data_dir / "ssq_records.json"

    def fetch_all(self):
        resp = requests = __import__('requests').requests
        r = requests.get(DATA_URL, params={
            "name": "ssq", "pageNo": 1, "pageSize": 5000, "systemType": "PC"
        }, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cwl.gov.cn/"}, timeout=30)
        data = r.json()
        if data.get("state") != 0:
            raise RuntimeError(data.get("message", "数据获取失败"))
        rows = []
        for item in data.get("result", []):
            reds = [int(x) for x in item["red"].split(",")]
            blue = int(item["blue"])
            prizes = {}
            for p in item.get("prizegrades", []):
                t = p.get("type")
                if t:
                    prizes[str(t)] = {"count": _to_int(p.get("typenum")), "money": _to_int(p.get("typemoney"))}
            rows.append({
                "code": item["code"], "date": item["date"], "week": item.get("week", ""),
                "red": sorted(reds), "blue": blue,
                "sales": _to_int(item.get("sales")),
                "poolmoney": _to_int(item.get("poolmoney")),
                "content": item.get("content", ""), "prizes": prizes,
            })
        rows.sort(key=lambda r: r["code"])
        return rows

    def save_cache(self, rows):
        self.history_file.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def load_cache(self):
        if self.history_file.exists():
            try: return json.loads(self.history_file.read_text(encoding="utf-8"))
            except: return []
        return []

    def get_data(self, n=100, refresh=False):
        rows = [] if refresh else self.load_cache()
        if len(rows) < n:
            try:
                rows = self.fetch_all()
                self.save_cache(rows)
            except Exception as e:
                print(f"[警告]联网失败: {e}")
                if not rows: rows = self.load_cache()
        if n >= len(rows): return rows
        return rows[-n:]

    def get_max_periods(self):
        try:
            rows = self.fetch_all()
            self.save_cache(rows)
            return len(rows)
        except:
            return len(self.load_cache())

    def load_records(self):
        if self.records_file.exists():
            try: return json.loads(self.records_file.read_text(encoding="utf-8"))
            except: return []
        return []

    def save_records(self, recs):
        self.records_file.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_record(self, code, date, red, blue, mult, amount, note=""):
        recs = self.load_records()
        rec = {
            "id": uuid.uuid4().hex[:12], "code": str(code), "date": str(date),
            "red": [int(x) for x in red], "blue": int(blue),
            "mult": int(mult) or 1, "amount": float(amount) or 2,
            "note": note, "checked": False, "win_grade": 0, "win_amount": 0, "status": "",
        }
        recs.append(rec)
        self.save_records(recs)
        return rec

    def delete_record(self, rid):
        recs = [r for r in self.load_records() if r.get("id") != rid]
        self.save_records(recs)

    def check_records(self, rows):
        by_code = {r["code"]: r for r in rows}
        total_in = total_win = checked_n = pending = 0
        recs = self.load_records()
        for rec in recs:
            mult = rec.get("mult", 1) or 1
            total_in += rec.get("amount", 0) or 0
            actual = by_code.get(rec.get("code", ""))
            if not actual:
                rec.update({"checked": False, "win_grade": 0, "win_amount": 0, "status": "未开奖"})
                pending += 1; continue
            rh = len(set(rec["red"]) & set(actual["red"]))
            bh = 1 if rec["blue"] == actual["blue"] else 0
            g = _judge(rh, bh)
            amt = (PRIZE_AMOUNT.get(g, 0) * mult) if g else 0
            rec.update({"checked": True, "win_grade": g, "win_amount": amt,
                        "red_hit": rh, "blue_hit": bh, "status": PRIZE_NAMES.get(g, "未中奖") if g else "未中奖"})
            total_win += amt; checked_n += 1
        self.save_records(recs)
        stats = {"total_in": total_in, "total_win": total_win, "net": total_win - total_in,
                 "checked": checked_n, "pending": pending, "count": len(recs)}
        return recs, stats


# ============================================================
# 分析算法 (复用自 ssq_analyzer.py)
# ============================================================

def _judge(red_hit, blue_hit):
    if red_hit == 6 and blue_hit: return 1
    if red_hit == 6: return 2
    if red_hit == 5 and blue_hit: return 3
    if red_hit == 5 or (red_hit == 4 and blue_hit): return 4
    if red_hit == 4 or (red_hit == 3 and blue_hit): return 5
    if blue_hit: return 6
    return 0


def frequency(rows, key):
    c = Counter()
    for r in rows:
        if key == "red": c.update(r["red"])
        else: c[r["blue"]] += 1
    return c


def omissions(rows, key, total):
    n = len(rows); omit = {}
    for num in range(1, total + 1):
        miss = 0
        for i in range(n - 1, -1, -1):
            hit = (num in rows[i]["red"]) if key == "red" else (num == rows[i]["blue"])
            if hit: break
            miss += 1
        omit[num] = miss
    return omit


def tail_freq(rows):
    c = Counter()
    for r in rows:
        for x in r["red"]: c[x % 10] += 1
    return c


def zone_freq(rows):
    c = Counter()
    for r in rows:
        for x in r["red"]: c[(x - 1) // 11] += 1
    return c


def red_scores(rows, w_freq=W_FREQ, w_omit=W_OMIT, w_tail=W_TAIL, w_zone=W_ZONE):
    freq = frequency(rows, "red"); omit = omissions(rows, "red", RED_COUNT)
    tails = tail_freq(rows); zones = zone_freq(rows)
    fn = norm(freq); on = norm(omit)
    tn = norm({i: tails[i % 10] for i in range(1, RED_COUNT + 1)})
    zn = norm({i: zones[(i - 1) // 11] for i in range(1, RED_COUNT + 1)})
    scores = {}
    for i in range(1, RED_COUNT + 1):
        scores[i] = w_freq * fn.get(i, 0) + w_omit * on.get(i, 0) + w_tail * tn[i] + w_zone * zn[i]
    return scores, {"freq": freq, "omit": omit, "tail": tails, "zone": zones}


def blue_scores(rows, w_freq=0.5, w_omit=0.5):
    freq = frequency(rows, "blue"); omit = omissions(rows, "blue", BLUE_COUNT)
    fn = norm(freq); on = norm(omit)
    scores = {i: w_freq * fn.get(i, 0) + w_omit * on.get(i, 0) for i in range(1, BLUE_COUNT + 1)}
    return scores, {"freq": freq, "omit": omit}


def check_constraints(reds):
    s = sorted(reds)
    if not (SUM_RANGE[0] <= sum(s) <= SUM_RANGE[1]): return False
    if not (ODD_RANGE[0] <= sum(1 for x in s if x % 2) <= ODD_RANGE[1]): return False
    if not (BIG_RANGE[0] <= sum(1 for x in s if x >= 18) <= BIG_RANGE[1]): return False
    if not (SPAN_RANGE[0] <= s[-1] - s[0] <= SPAN_RANGE[1]): return False
    run = mx = 1
    for a, b in zip(s, s[1:]): run = run + 1 if b - a == 1 else 1; mx = max(mx, run)
    if mx > MAX_CONSEC: return False
    if max(Counter((x - 1) // 11 for x in s).values()) > ZONE_MAX_IN_ONE: return False
    return True


def draw_weighted(scores, k, tries=2000):
    nums = list(scores.keys()); weights = [scores[x] + 1e-6 for x in nums]
    for _ in range(tries):
        picked = sorted(random.choices(nums, weights=weights, k=k))
        if len(set(picked)) == k and check_constraints(picked): return picked
    return sorted(random.sample(nums, k))


def draw_n(scores, m):
    nums = list(scores.keys()); weights = [scores[x] + 1e-6 for x in nums]
    while True:
        picked = random.choices(nums, weights=weights, k=m)
        if len(set(picked)) == m: return sorted(picked)


def _one_backtest(rows, train_len, k, rounds, use_strategy, rw=None, bw=None):
    rw = rw or {}; bw = bw or {}
    grades = Counter(); total_red_hit = total_blue_hit = total = 0
    for i in range(train_len, len(rows)):
        train = rows[i - train_len:i]; actual = rows[i]
        if use_strategy:
            red_sc, _ = red_scores(train, **rw); blue_sc, _ = blue_scores(train, **bw)
        for _ in range(rounds):
            for _ in range(k):
                if use_strategy:
                    reds = draw_weighted(red_sc, RED_PICK)
                    blue = random.choices(list(blue_sc.keys()), weights=[blue_sc[x] + 1e-6 for x in blue_sc], k=1)[0]
                else:
                    reds = random.sample(range(1, RED_COUNT + 1), RED_PICK)
                    blue = random.randint(1, BLUE_COUNT)
                rh = len(set(reds) & set(actual["red"])); bh = 1 if blue == actual["blue"] else 0
                grades[_judge(rh, bh)] += 1; total_red_hit += rh; total_blue_hit += bh; total += 1
    win = sum(v for g, v in grades.items() if g >= 1)
    return {"periods": len(rows) - train_len, "rounds": rounds, "total": total,
            "grades": grades, "win": win, "win_rate": win / total if total else 0,
            "avg_red": total_red_hit / total if total else 0, "blue_rate": total_blue_hit / total if total else 0}


# ============================================================
# 图表工具
# ============================================================

CHART_DIR = None

def _gen_chart(fig_func, fname):
    """用 matplotlib 生成图表，保存为 PNG，返回文件路径"""
    global CHART_DIR
    if CHART_DIR is None:
        CHART_DIR = Path(__file__).parent / ".charts"
    CHART_DIR.mkdir(exist_ok=True)
    fpath = CHART_DIR / fname
    fig = fig_func()
    fig.savefig(str(fpath), dpi=120, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return str(fpath)


def chart_freq(freq):
    return _gen_chart(lambda: _plot_bar(freq, "红球出现频率"), "chart_freq.png")

def chart_omit(omit):
    return _gen_chart(lambda: _plot_bar(omit, "红球遗漏值"), "chart_omit.png")

def chart_score(scores):
    return _gen_chart(lambda: _plot_bar(scores, "红球综合评分"), "chart_score.png")

def chart_tail_freq(tails):
    return _gen_chart(lambda: _plot_bar(tails, "尾数频率"), "chart_tail.png")

def chart_zone_freq(zones):
    z_names = {"0": "01-11", "1": "12-22", "2": "23-33"}
    return _gen_chart(lambda: _plot_bar(zones, "区间出号", labels=z_names), "chart_zone.png")

def chart_blue_freq(freq):
    return _gen_chart(lambda: _plot_bar(freq, "蓝球出现频率"), "chart_bfreq.png")

def chart_backtest(strat_g, rand_g):
    return _gen_chart(lambda: _plot_backtest(strat_g, rand_g), "chart_backtest.png")


def _plot_bar(d, title, labels=None):
    fig, ax = plt.subplots(figsize=(8, 3.5))
    keys = sorted(d.keys())
    vals = [d[k] for k in keys]
    lbls = [labels.get(str(k), str(k)) if labels else str(k) for k in keys]
    ax.bar(lbls, vals, color='#3498DB', edgecolor='none')
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.set_xlabel('')
    for lab in ax.xaxis.get_ticklabels(): lab.set_rotation(45)
    plt.tight_layout()
    return fig


def _plot_backtest(sg, rg):
    fig, ax = plt.subplots(figsize=(8, 4))
    g_names = ['未中', '六等', '五等', '四等', '三等', '二等', '一等']
    sx = [sg.get(i, 0) for i in range(7)]
    rx = [rg.get(i, 0) for i in range(7)]
    x = range(7)
    w = 0.35
    ax.bar([i - w for i in x], sx, w, label='策略', color='#E74C3C')
    ax.bar([i + w for i in x], rx, w, label='随机', color='#3498DB')
    ax.set_xticks(list(x)); ax.set_xticklabels(g_names)
    ax.set_title('回测对比', fontsize=12, fontweight='bold')
    ax.legend()
    plt.tight_layout()
    return fig


# ============================================================
# UI 辅助
# ============================================================

def _ball_label(text, color, bg):
    """圆形球号标签"""
    lbl = Label(text=text, font_size='16sp', bold=True, color=(1, 1, 1, 1),
                size_hint=(None, None), size=('48dp', '48dp'), halign='center', valign='middle')
    with lbl.canvas.before:
        Color(*bg)
        lbl.bg_rect = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[24])
    lbl.bind(pos=lambda *a: setattr(lbl.bg_rect, 'pos', a[1].pos),
             size=lambda *a: setattr(lbl.bg_rect, 'size', a[1].size))
    return lbl


def _section_box(child, **kw):
    """分区容器"""
    box = BoxLayout(orientation='vertical', size_hint_y=None, **kw)
    box.bind(minimum_height=box.setter('height'))
    outer = BoxLayout(orientation='vertical', size_hint_y=None, height=child.height + 20, padding=10,
                      spacing=5, background_color=(0.96, 0.96, 0.96, 1))
    with outer.canvas.before:
        Color(1, 1, 1, 1)
        outer.bg = RoundedRectangle(pos=outer.pos, size=outer.size, radius=[8])
    outer.bind(pos=lambda *a: setattr(outer.bg, 'pos', a[1].pos),
               size=lambda *a: setattr(outer.bg, 'size', a[1].size))
    outer.add_widget(child)
    return outer


def _title_row(text):
    lbl = Label(text=text, font_size='15sp', bold=True, color=DARK, size_hint_y=None, height='30dp')
    return lbl


def _row(*widgets, **kw):
    h = kw.get('height', '40dp')
    box = BoxLayout(size_hint_y=None, height=h, spacing=8, **kw)
    for w in widgets: box.add_widget(w)
    return box


# ============================================================
# 屏幕：概览
# ============================================================

class OverviewScreen(Screen):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.root = BoxLayout(orientation='vertical')
        self.scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self.content.add_widget(_title_row("最新开奖"))
        rows = self.dm.get_data(1)
        if rows:
            r = rows[-1]
            line = BoxLayout(size_hint_y=None, height='60dp', spacing=10)
            for x in r["red"]: line.add_widget(_ball_label(f"{x:02d}", 1, RED))
            line.add_widget(_ball_label(f"{r['blue']:02d}", 1, BLUE))
            self.content.add_widget(line)
            info = Label(text=f"第 {r['code']} 期  {r['date']} {r.get('week', '')}\n"
                         f"销售额: {r.get('sales', 0)//10000}万  奖池: {r.get('poolmoney', 0)//10000}万",
                         size_hint_y=None, height='50dp', color=GRAY)
            self.content.add_widget(info)
        else:
            self.content.add_widget(Label(text="暂无数据", color=GRAY, size_hint_y=None, height='40dp'))

        self.content.add_widget(_title_row("热号 / 冷号"))
        rows = self.dm.get_data(100)
        freq = frequency(rows, "red"); omit = omissions(rows, "red", RED_COUNT)
        hot = sorted(range(1, RED_COUNT + 1), key=lambda i: -freq[i])[:10]
        cold = sorted(range(1, RED_COUNT + 1), key=lambda i: -omit[i])[:10]
        bfreq = frequency(rows, "blue"); bomit = omissions(rows, "blue", BLUE_COUNT)
        bhot = sorted(range(1, BLUE_COUNT + 1), key=lambda i: -bfreq[i])[:5]
        bcold = sorted(range(1, BLUE_COUNT + 1), key=lambda i: -bomit[i])[:5]

        hbox = BoxLayout(size_hint_y=None, height='48dp', spacing=5)
        for x in hot: hbox.add_widget(_ball_label(f"{x:02d}", 1, RED))
        self.content.add_widget(_section_box(hbox))

        hbox2 = BoxLayout(size_hint_y=None, height='48dp', spacing=5)
        for x in cold: hbox2.add_widget(_ball_label(f"{x:02d}", 1, (0.5, 0.5, 0.5, 1)))
        self.content.add_widget(_section_box(hbox2))

        bline = BoxLayout(size_hint_y=None, height='48dp', spacing=5)
        for x in bhot: bline.add_widget(_ball_label(f"{x:02d}", 1, BLUE))
        self.content.add_widget(_section_box(bline))

        self.content.add_widget(_title_row("图表"))
        paths = []
        try:
            paths.append(chart_freq(freq))
            paths.append(chart_omit(omit))
            paths.append(chart_blue_freq(bfreq))
        except Exception as e:
            print(f"图表生成失败: {e}")

        for p in paths:
            if p and os.path.exists(p):
                self.content.add_widget(Image(source=p, size_hint_y=None, height='200dp', allow_stretch=True, keep_ratio=True))

        self.content.add_widget(Label(size_hint_y=None, height='40dp'))
        self.content.add_widget(Label(text="策略不提高中奖概率，理性购彩", size_hint_y=None, height='30dp',
                                       color=GRAY, font_size='11sp', halign='center'))


# ============================================================
# 屏幕：分析
# ============================================================

class AnalysisScreen(Screen):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.root = BoxLayout(orientation='vertical')
        self.scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='static', size_hint_y=None, padding=10, spacing=10) if False else \
            BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        n_sp = Spinner(text="100", values=[str(i) for i in range(50, 1001, 50)],
                       size_hint_x=0.3, height='40dp', pos_hint={'center_y': 0.5})
        btn = Button(text="刷新数据", size_hint_x=0.2, height='40dp',
                     pos_hint={'center_y': 0.5}, background_color=BLUE, color=(1, 1, 1, 1))
        top = BoxLayout(size_hint_y=None, height='44dp', spacing=8)
        top.add_widget(Label(text="期数:", size_hint_x=0.15, height='40dp', pos_hint={'center_y': 0.5}))
        top.add_widget(n_sp)
        top.add_widget(btn)
        self.content.add_widget(top)

        def on_refresh(*args):
            n = int(n_sp.text)
            rows = self.dm.get_data(n)
            self._build(rows, n)

        btn.bind(on_press=on_refresh)
        rows = self.dm.get_data(100)
        self._build(rows, 100)

    def _build(self, rows, n):
        self.content.clear_widgets()
        # 保留顶部栏
        n_sp = Spinner(text=str(n), values=[str(i) for i in range(50, 1001, 50)],
                       size_hint_x=0.3, height='40dp', pos_hint={'center_y': 0.5})
        btn = Button(text="刷新数据", size_hint_x=0.2, height='40dp',
                     pos_hint={'center_y': 0.5}, background_color=BLUE, color=(1, 1, 1, 1))
        top = BoxLayout(size_hint_y=None, height='44dp', spacing=8)
        top.add_widget(Label(text="期数:", size_hint_x=0.15, height='40dp', pos_hint={'center_y': 0.5}))
        top.add_widget(n_sp)
        top.add_widget(btn)
        self.content.add_widget(top)

        def on_refresh(*args):
            n2 = int(n_sp.text)
            rows2 = self.dm.get_data(n2)
            self._build(rows2, n2)
        btn.bind(on_press=on_refresh)

        red_sc, rs = red_scores(rows)
        bsc, bs = blue_scores(rows)

        self.content.add_widget(_title_row(f"红球综合评分（近 {n} 期）"))
        self.content.add_widget(Label(text=f"权重: 频率{W_FREQ} + 遗漏{W_OMIT} + 尾数{W_TAIL} + 区间{W_ZONE}",
                                       size_hint_y=None, height='28dp', color=GRAY, font_size='11sp'))

        score_grid = GridLayout(cols=8, size_hint_y=None, height='120dp', spacing=3)
        for i in range(1, RED_COUNT + 1):
            v = red_sc[i]
            mx = max(red_sc.values())
            ratio = v / mx if mx else 0
            r = int(ratio * 231)
            g = int((1 - ratio) * 52)
            b = 0
            lbl = Label(text=f"{i:02d}\n{v:.2f}", font_size='10sp', color=(1, 1, 1, 1),
                        size_hint=(None, None), size=('52dp', '42dp'), halign='center', valign='middle')
            with lbl.canvas.before:
                Color(r / 255, g / 255, b, 1)
                lbl.bg_r = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[4])
            lbl.bind(pos=lambda *a: [setattr(x, 'pos', a[1].pos) for x in [a[1].bg_r]],
                     size=lambda *a: [setattr(x, 'size', a[1].size) for x in [a[1].bg_r]])
            score_grid.add_widget(lbl)
        self.content.add_widget(score_grid)

        self.content.add_widget(_title_row("蓝球评分"))
        bline = BoxLayout(size_hint_y=None, height='44dp', spacing=3)
        for i in range(1, BLUE_COUNT + 1):
            v = bsc[i]
            mx = max(bsc.values())
            ratio = v / mx if mx else 0
            g = int((1 - ratio) * 150)
            lbl = Label(text=f"{i:02d}\n{v:.2f}", font_size='10sp', color=(1, 1, 1, 1),
                        size_hint=(None, None), size=('42dp', '36dp'), halign='center', valign='middle')
            with lbl.canvas.before:
                Color(0.2, g / 255, 0.9, 1)
                lbl.bg_b = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[4])
            lbl.bind(pos=lambda *a: [setattr(x, 'pos', a[1].pos) for x in [a[1].bg_b]],
                     size=lambda *a: [setattr(x, 'size', a[1].size) for x in [a[1].bg_b]])
            bline.add_widget(lbl)
        self.content.add_widget(_section_box(bline))

        self.content.add_widget(_title_row("图表"))
        charts = []
        try:
            charts.append(("频率", chart_freq(rs["freq"])))
            charts.append(("遗漏", chart_omit(rs["omit"])))
            charts.append(("尾数", chart_tail_freq(rs["tail"])))
            charts.append(("区间", chart_zone_freq(rs["zone"])))
            charts.append(("蓝球频率", chart_blue_freq(bs["freq"])))
        except Exception as e:
            print(f"图表失败: {e}")
        for name, p in charts:
            if p and os.path.exists(p):
                self.content.add_widget(Image(source=p, size_hint_y=None, height='200dp', allow_stretch=True, keep_ratio=True))

        # 最新开奖
        self.content.add_widget(_title_row("历史开奖"))
        hist_grid = BoxLayout(orientation='vertical', size_hint_y=None, height=min(300, max(80, n * 12)))
        for r in reversed(rows[-min(20, len(rows)):]):
            line = BoxLayout(size_hint_y=None, height='32dp', spacing=5)
            line.add_widget(Label(text=f"[{r['code']}]", size_hint_x=0.25, height='28dp', font_size='10sp', color=GRAY))
            for x in r["red"]: line.add_widget(_ball_label(f"{x:02d}", 0.8, RED))
            line.add_widget(_ball_label(f"{r['blue']:02d}", 0.8, BLUE))
            hist_grid.add_widget(line)
        self.content.add_widget(hist_grid)
        self.content.add_widget(Label(size_hint_y=None, height='50dp'))


# ============================================================
# 屏幕：选号
# ============================================================

class GenerateScreen(Screen):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.root = BoxLayout(orientation='vertical')
        self.scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self._build()

    def _build(self):
        self.content.clear_widgets()
        self.content.add_widget(_title_row("玩法"))
        self.play_spinner = Spinner(text="单式", values=["单式", "红球复式", "蓝球复式", "全复式"],
                                     size_hint_x=0.5, height='40dp')
        self.content.add_widget(_row(self.play_spinner))

        self.content.add_widget(_title_row("权重设置"))
        w_grid = GridLayout(cols=2, size_hint_y=None, height='160dp', spacing=5)
        self.w_freq_s = Slider(min=0, max=1, value=W_FREQ, size_hint_x=0.7)
        self.w_freq_l = Label(text=f"频率: {W_FREQ}", size_hint_x=0.3, height='30dp')
        self.w_freq_s.bind(value=lambda *a: setattr(self.w_freq_l, 'text', f"频率: {a[1]:.2f}"))
        w_grid.add_widget(self.w_freq_l); w_grid.add_widget(self.w_freq_s)

        self.w_omit_s = Slider(min=0, max=1, value=W_OMIT, size_hint_x=0.7)
        self.w_omit_l = Label(text=f"遗漏: {W_OMIT}", size_hint_x=0.3, height='30dp')
        self.w_omit_s.bind(value=lambda *a: setattr(self.w_omit_l, 'text', f"遗漏: {a[1]:.2f}"))
        w_grid.add_widget(self.w_omit_l); w_grid.add_widget(self.w_omit_s)

        self.w_tail_s = Slider(min=0, max=1, value=W_TAIL, size_hint_x=0.7)
        self.w_tail_l = Label(text=f"尾数: {W_TAIL}", size_hint_x=0.3, height='30dp')
        self.w_tail_s.bind(value=lambda *a: setattr(self.w_tail_l, 'text', f"尾数: {a[1]:.2f}"))
        w_grid.add_widget(self.w_tail_l); w_grid.add_widget(self.w_tail_s)

        self.w_zone_s = Slider(min=0, max=1, value=W_ZONE, size_hint_x=0.7)
        self.w_zone_l = Label(text=f"区间: {W_ZONE}", size_hint_x=0.3, height='30dp')
        self.w_zone_s.bind(value=lambda *a: setattr(self.w_zone_l, 'text', f"区间: {a[1]:.2f}"))
        w_grid.add_widget(self.w_zone_l); w_grid.add_widget(self.w_zone_s)
        self.content.add_widget(w_grid)

        self.content.add_widget(_title_row("约束条件"))
        c_grid = GridLayout(cols=2, size_hint_y=None, height='200dp', spacing=5)
        self.c_sum = TextInput(text=f"{SUM_RANGE[0]}-{SUM_RANGE[1]}", multiline=False,
                                hint_text="和值区间", size_hint_x=1, height='36dp')
        self.c_odd = TextInput(text=f"{ODD_RANGE[0]}-{ODD_RANGE[1]}", multiline=False,
                                hint_text="奇数个数", size_hint_x=1, height='36dp')
        self.c_big = TextInput(text=f"{BIG_RANGE[0]}-{BIG_RANGE[1]}", multiline=False,
                                hint_text="大号个数(>=18)", size_hint_x=1, height='36dp')
        self.c_span = TextInput(text=f"{SPAN_RANGE[0]}-{SPAN_RANGE[1]}", multiline=False,
                                 hint_text="跨度区间", size_hint_x=1, height='36dp')
        self.c_consec = TextInput(text=str(MAX_CONSEC), multiline=False,
                                   hint_text="最长连号", size_hint_x=1, height='36dp')
        self.c_zone = TextInput(text=str(ZONE_MAX_IN_ONE), multiline=False,
                                 hint_text="单区最多号数", size_hint_x=1, height='36dp')
        for w in [self.c_sum, self.c_odd, self.c_big, self.c_span, self.c_consec, self.c_zone]:
            c_grid.add_widget(w)
        self.content.add_widget(c_grid)

        self.content.add_widget(_title_row("生成设置"))
        self.tickets_spin = Spinner(text="5", values=[str(i) for i in range(1, 21)],
                                     size_hint_x=0.3, height='40dp')
        self.n_spin = Spinner(text="100", values=[str(i) for i in range(50, 1001, 50)],
                               size_hint_x=0.3, height='40dp')
        self.content.add_widget(_row(Label(text="注数:", height='40dp'), self.tickets_spin,
                                      Label(text="期数:", height='40dp'), self.n_spin))

        self.gen_btn = Button(text="开始选号", size_hint_y=None, height='50dp',
                               background_color=ACCENT, color=(1, 1, 1, 1), font_size='18sp')
        self.gen_btn.bind(on_press=self._generate)
        self.content.add_widget(self.gen_btn)

        self.result_box = BoxLayout(orientation='vertical', size_hint_y=None, height='10dp', spacing=5)
        self.content.add_widget(self.result_box)

        self.content.add_widget(Label(size_hint_y=None, height='60dp'))

    def _get_constraints(self):
        def _parse_range(s):
            parts = s.split('-')
            return (int(parts[0]), int(parts[1])) if len(parts) == 2 else None
        cons = {}
        v = self.c_sum.text
        if '-' in v:
            r = _parse_range(v)
            if r: cons['sum_range'] = r
        v = self.c_odd.text
        if '-' in v:
            r = _parse_range(v)
            if r: cons['odd_range'] = r
        v = self.c_big.text
        if '-' in v:
            r = _parse_range(v)
            if r: cons['big_range'] = r
        v = self.c_span.text
        if '-' in v:
            r = _parse_range(v)
            if r: cons['span_range'] = r
        try: cons['max_consec'] = int(self.c_consec.text)
        except: pass
        try: cons['zone_max'] = int(self.c_zone.text)
        except: pass
        return cons

    def _generate(self, *args):
        self.gen_btn.disabled = True
        self.gen_btn.text = "生成中..."
        self.result_box.clear_widgets()

        def _do():
            play = {"单式": "single", "红球复式": "red_dup", "蓝球复式": "blue_dup", "全复式": "full_dup"}[self.play_spinner.text]
            rw = {"w_freq": self.w_freq_s.value, "w_omit": self.w_omit_s.value,
                  "w_tail": self.w_tail_s.value, "w_zone": self.w_zone_s.value}
            cons = self._get_constraints()
            n = int(self.n_spin.text)
            rows = self.dm.get_data(n)
            red_sc, _ = red_scores(rows, **rw)
            bsc, _ = blue_scores(rows)
            blues = list(bsc.keys()); bweights = [bsc[x] + 1e-6 for x in blues]

            def pick_blue():
                return random.choices(blues, weights=bweights, k=1)[0]

            def expand(reds, blues_list):
                from itertools import combinations
                tickets = []
                for r in combinations(sorted(reds), 6):
                    for b in blues_list:
                        tickets.append({"red": [int(x) for x in r], "blue": int(b)})
                return tickets

            if play == "single":
                ntk = int(self.tickets_spin.text)
                result = []
                for _ in range(ntk):
                    reds = draw_weighted(red_sc, RED_PICK, **cons)
                    result.append({"red": reds, "blue": pick_blue()})
            elif play == "red_dup":
                reds = draw_n(red_sc, 8)
                blue = pick_blue()
                result = expand(reds, [blue])
            elif play == "blue_dup":
                reds = draw_weighted(red_sc, RED_PICK, **cons)
                blues_sel = sorted(int(x) for x in draw_n(bsc, 3))
                result = expand(reds, blues_sel)
            else:
                reds = draw_n(red_sc, 8)
                blues_sel = sorted(int(x) for x in draw_n(bsc, 3))
                result = expand(reds, blues_sel)

            @mainthread
            def _show():
                self.result_box.clear_widgets()
                self.result_box.height = len(result) * 40 + 20
                self.result_box.add_widget(_title_row(f"生成 {len(result)} 注"))
                for i, t in enumerate(result):
                    line = BoxLayout(size_hint_y=None, height='36dp', spacing=5)
                    line.add_widget(Label(text=f"{i + 1:02d}", size_hint_x=0.1, height='32dp', font_size='11sp'))
                    for x in t["red"]: line.add_widget(_ball_label(f"{x:02d}", 0.9, RED))
                    line.add_widget(_ball_label(f"{t['blue']:02d}", 0.9, BLUE))
                    self.result_box.add_widget(line)
                self.gen_btn.disabled = False
                self.gen_btn.text = "开始选号"
                self.content.scroll_to(self.result_box)

            _show()

        threading.Thread(target=_do, daemon=True).start()


# ============================================================
# 屏幕：回测
# ============================================================

class BacktestScreen(Screen):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.root = BoxLayout(orientation='vertical')
        self.scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self._build()

    def _build(self):
        self.content.clear_widgets()
        self.content.add_widget(_title_row("回测参数"))
        g = GridLayout(cols=2, size_hint_y=None, height='200dp', spacing=8)
        g.add_widget(Label(text="训练窗口(期):", height='36dp')); self.train = TextInput(text="50", multiline=False, height='36dp')
        g.add_widget(Label(text="每期注数:", height='36dp')); self.k = TextInput(text="5", multiline=False, height='36dp')
        g.add_widget(Label(text="轮次:", height='36dp')); self.rounds = TextInput(text="10", multiline=False, height='36dp')
        g.add_widget(Label(text="数据期数:", height='36dp')); self.n = TextInput(text="200", multiline=False, height='36dp')
        for w in [self.train, self.k, self.rounds, self.n]:
            w.input_filter = 'int'
        for w in [self.train, self.k, self.rounds, self.n]:
            g.add_widget(w)
        self.content.add_widget(g)

        self.bt_btn = Button(text="开始回测", size_hint_y=None, height='50dp',
                              background_color=BLUE, color=(1, 1, 1, 1), font_size='18sp')
        self.bt_btn.bind(on_press=self._run)
        self.content.add_widget(self.bt_btn)

        self.bt_result = BoxLayout(orientation='vertical', size_hint_y=None, height='10dp', spacing=5)
        self.content.add_widget(self.bt_result)
        self.content.add_widget(Label(size_hint_y=None, height='60dp'))

    def _run(self, *args):
        self.bt_btn.disabled = True
        self.bt_btn.text = "回测中..."
        self.bt_result.clear_widgets()

        def _do():
            try:
                tl = int(self.train.text); k = int(self.k.text); rnd = int(self.rounds.text); n = int(self.n.text)
            except:
                @mainthread
                def _err():
                    self.bt_btn.disabled = False; self.bt_btn.text = "开始回测"
                    self.bt_result.add_widget(Label(text="参数错误", color=(1, 0, 0, 1)))
                _err(); return

            rows = self.dm.get_data(n)
            strat = _one_backtest(rows, tl, k, rnd, True)
            rand = _one_backtest(rows, tl, k, rnd, False)

            @mainthread
            def _show():
                self.bt_result.clear_widgets()
                self.bt_result.height = 300

                g_names = ["未中奖", "六等奖", "五等奖", "四等奖", "三等奖", "二等奖", "一等奖"]

                def _show_result(title, s):
                    box = BoxLayout(orientation='vertical', size_hint_y=None, height='120dp')
                    box.add_widget(Label(text=title, font_size='13sp', bold=True, size_hint_y=None, height='28dp'))
                    lines = [
                        f"回测期数: {s['periods']}  总计: {s['total']} 注",
                        f"中奖: {s['win']} 注 ({s['win_rate'] * 100:.1f}%)",
                        f"平均红球命中: {s['avg_red']:.2f}  蓝球命中率: {s['blue_rate'] * 100:.1f}%",
                    ]
                    for txt in lines:
                        box.add_widget(Label(text=txt, size_hint_y=None, height='24dp', font_size='11sp', color=GRAY))
                    self.bt_result.add_widget(box)

                _show_result("【策略选号】", strat)
                _show_result("【纯随机对照】", rand)

                # 图表
                try:
                    p = chart_backtest(strat['grades'], rand['grades'])
                    if p and os.path.exists(p):
                        self.bt_result.add_widget(Image(source=p, size_hint_y=None, height='200dp'))
                except: pass

                self.bt_result.height = self.bt_result.minimum_height
                self.bt_btn.disabled = False
                self.bt_btn.text = "开始回测"
                self.content.scroll_to(self.bt_result)

            _show()

        threading.Thread(target=_do, daemon=True).start()


# ============================================================
# 屏幕：购彩记录
# ============================================================

class RecordsScreen(Screen):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.root = BoxLayout(orientation='vertical')
        self.scroll = ScrollView(do_scroll_x=False)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self._show_stats()
        self._show_add_form()
        self._show_list()

    def _show_stats(self):
        rows = self.dm.get_data(100000)
        recs, stats = self.dm.check_records(rows)
        box = BoxLayout(orientation='vertical', size_hint_y=None, height='90dp', padding=5, spacing=2)
        box.add_widget(Label(text="统计", font_size='14sp', bold=True, size_hint_y=None, height='28dp'))
        box.add_widget(Label(text=f"总注数: {stats['count']}  待开奖: {stats['pending']}",
                              size_hint_y=None, height='24dp', font_size='11sp', color=GRAY))
        net_str = f"净盈亏: {stats['net']:+.0f}元"
        box.add_widget(Label(text=f"投入: {stats['total_in']:.0f}元  中奖: {stats['total_win']:.0f}元  {net_str}",
                              size_hint_y=None, height='24dp', font_size='11sp',
                              color=ACCENT if stats['net'] >= 0 else RED))
        self.content.add_widget(box)

    def _show_add_form(self):
        box = BoxLayout(orientation='vertical', size_hint_y=None, height='240dp', padding=5, spacing=5)
        box.add_widget(Label(text="添加记录", font_size='14sp', bold=True, size_hint_y=None, height='28dp'))

        self.add_code = TextInput(hint_text="期号，如 2026098", multiline=False, height='36dp', size_hint_x=1)
        self.add_date = TextInput(text=today_str(), hint_text="日期", multiline=False, height='36dp', size_hint_x=1)
        self.add_red = TextInput(hint_text="红球，空格分隔，如 03 08 12 18 25 30", multiline=False, height='36dp', size_hint_x=1)
        self.add_blue = TextInput(hint_text="蓝球，如 07", multiline=False, height='36dp', size_hint_x=1)
        self.add_mult = TextInput(text="1", hint_text="倍数", multiline=False, height='36dp', size_hint_x=0.3, input_filter='int')
        self.add_note = TextInput(hint_text="备注（选填）", multiline=False, height='36dp', size_hint_x=0.7)

        for w in [self.add_code, self.add_date, self.add_red, self.add_blue, self.add_mult, self.add_note]:
            box.add_widget(w)

        btn = Button(text="保存记录", size_hint_y=None, height='44dp',
                      background_color=ACCENT, color=(1, 1, 1, 1))
        btn.bind(on_press=self._save_record)
        box.add_widget(btn)
        self.content.add_widget(box)

    def _save_record(self, *args):
        try:
            code = self.add_code.text.strip()
            red = [int(x) for x in self.add_red.text.strip().split()]
            blue = int(self.add_blue.text.strip())
            if len(red) != 6:
                self._popup("提示", "红球必须是 6 个号码")
                return
            if not (1 <= min(red) and max(red) <= 33):
                self._popup("提示", "红球号码范围 01-33")
                return
            if not (1 <= blue <= 16):
                self._popup("提示", "蓝球号码范围 01-16")
                return
            self.dm.add_record(code, self.add_date.text, red, blue,
                               int(self.add_mult.text) or 1, (int(self.add_mult.text) or 1) * 2,
                               self.add_note.text)
            self.add_red.text = ""; self.add_blue.text = ""; self.add_note.text = ""
            self.refresh()
        except Exception as e:
            self._popup("错误", str(e))

    def _show_list(self):
        rows = self.dm.get_data(100000)
        recs, _ = self.dm.check_records(rows)
        if not recs:
            self.content.add_widget(Label(text="暂无记录", color=GRAY, size_hint_y=None, height='60dp'))
            return
        self.content.add_widget(_title_row(f"购彩记录 ({len(recs)} 条)"))
        for rec in reversed(recs[-50:]):
            card = BoxLayout(orientation='vertical', size_hint_y=None, height='56dp',
                              padding=5, spacing=2, background_color=(1, 1, 1, 1))
            with card.canvas.before:
                Color(1, 1, 1, 1)
                card.bg = RoundedRectangle(pos=card.pos, size=card.size, radius=[6])
            card.bind(pos=lambda *a: setattr(a[1].bg, 'pos', a[1].pos),
                      size=lambda *a: setattr(a[1].bg, 'size', a[1].size))
            top = BoxLayout(size_hint_y=None, height='26dp', spacing=5)
            top.add_widget(Label(text=f"{rec.get('code', '?')}  {rec.get('date', '')}",
                                  size_hint_x=0.35, height='24dp', font_size='10sp'))
            st = rec.get('status', '未开奖')
            clr = ACCENT if '一' in st or '二' in st or '三' in st else (RED if '未中奖' in st else GRAY)
            top.add_widget(Label(text=st, size_hint_x=0.35, height='24dp', font_size='10sp', color=clr))
            top.add_widget(Label(text=f"{rec.get('win_amount', 0):.0f}元", size_hint_x=0.15, height='24dp',
                                  font_size='10sp', color=ACCENT if rec.get('win_amount', 0) > 0 else GRAY))
            del_btn = Button(text="×", size_hint_x=0.15, height='24dp', font_size='14sp',
                              background_color=(0.95, 0.95, 0.95, 1), color=(0.7, 0.7, 0.7, 1))
            rid = rec['id']
            del_btn.bind(on_press=lambda *a, r=rid: self._del_record(r))
            top.add_widget(del_btn)
            card.add_widget(top)
            balls = BoxLayout(size_hint_y=None, height='26dp', spacing=3)
            for x in rec.get("red", []): balls.add_widget(_ball_label(f"{x:02d}", 0.85, RED))
            balls.add_widget(_ball_label(f"{rec.get('blue', 0):02d}", 0.85, BLUE))
            rh = rec.get('red_hit', '?')
            bh = rec.get('blue_hit', '?')
            balls.add_widget(Label(text=f"红:{rh} 蓝:{bh}", size_hint_x=0.2, height='24dp', font_size='10sp', color=GRAY))
            card.add_widget(balls)
            self.content.add_widget(card)
        self.content.add_widget(Label(size_hint_y=None, height='60dp'))

    def _del_record(self, rid):
        self.dm.delete_record(rid)
        self.refresh()

    def _popup(self, title, msg):
        popup = Popup(title=title, content=Label(text=msg, size_hint=(1, 1)),
                      size_hint=(0.8, 0.4))
        popup.open()


# ============================================================
# Tab 导航栏
# ============================================================

class TabBar(GridLayout):
    def __init__(self, sm, **kw):
        super().__init__(**kw)
        self.cols = 5
        self.size_hint_y = None
        self.height = '50dp'
        self.row_default_height = '50dp'
        self.tab_labels = []
        tabs = [("概览", sm), ("分析", sm), ("选号", sm), ("回测", sm), ("记录", sm)]
        for i, (name, _) in enumerate(tabs):
            btn = Button(text=name, font_size='14sp', background_color=get_color_from_hex("#F0F0F0"),
                          color=DARK, border_radius=0)
            btn.bind(on_press=lambda *a, idx=i: self._switch(idx))
            self.tab_labels.append(btn)
            self.add_widget(btn)

    def _switch(self, idx):
        # handled by parent
        pass


# ============================================================
# App
# ============================================================

class SSQApp(App):
    title = "双色球选号"

    def build(self):
        # data dir
        if sys.platform == 'android':
            from android import storage
            data_dir = storage.get_app_dir()
        else:
            data_dir = str(Path(__file__).parent / ".ssq_data")

        self.dm = DataManager(data_dir)

        # screens
        sm = ScreenManager()
        sm.add_widget(OverviewScreen(self.dm, name='overview'))
        sm.add_widget(AnalysisScreen(self.dm, name='analysis'))
        sm.add_widget(GenerateScreen(self.dm, name='generate'))
        sm.add_widget(BacktestScreen(self.dm, name='backtest'))
        sm.add_widget(RecordsScreen(self.dm, name='records'))

        # main layout
        main = BoxLayout(orientation='vertical')
        main.add_widget(sm)

        # tab bar
        tb = TabBar(sm)
        # wire tabs to screen switching
        tab_names = ['overview', 'analysis', 'generate', 'backtest', 'records']
        for i, btn in enumerate(tb.tab_labels):
            idx = i
            btn.bind(on_press=lambda *a, i=idx: setattr(sm, 'current', tab_names[i]))
        main.add_widget(tb)

        # highlight first tab
        tb.tab_labels[0].background_color = BLUE
        tb.tab_labels[0].color = (1, 1, 1, 1)

        def _on_current(inst, val):
            for i, btn in enumerate(tb.tab_labels):
                if tab_names[i] == val:
                    btn.background_color = BLUE
                    btn.color = (1, 1, 1, 1)
                else:
                    btn.background_color = get_color_from_hex("#F0F0F0")
                    btn.color = DARK
        sm.bind(current=_on_current)

        return main


if __name__ == '__main__':
    SSQApp().run()
