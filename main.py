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
import requests
from collections import Counter
from datetime import datetime
from pathlib import Path

from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.image import Image
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock, mainthread
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.core.window import Window

Window.clearcolor = (0.961, 0.965, 0.973, 1)

# ============================================================
# 中文字体注册 (Kivy 默认字体不含中文，需注册 simhei 避免方块)
# ============================================================
from kivy.core.text import LabelBase, DEFAULT_FONT
from kivy.utils import platform as _kivy_platform

def _register_cjk_font():
    """注册中文字体，让界面中文正常显示。"""
    candidates = []
    if _kivy_platform == 'android':
        candidates = [
            '/system/fonts/DroidSansFallback.ttf',
            '/system/fonts/NotoSansCJK-Regular.ttc',
            'simhei.ttf',
        ]
    else:
        candidates = ['simhei.ttf', 'msyh.ttc', 'C:/Windows/Fonts/simhei.ttf']
    for path in candidates:
        if path and os.path.exists(path):
            try:
                LabelBase.register(DEFAULT_FONT, path)
                return path
            except Exception:
                continue
    return None

_font_registered = _register_cjk_font()

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

RED = get_color_from_hex("#E53935")
RED_LIGHT = get_color_from_hex("#EF9A9A")
BLUE = get_color_from_hex("#1565C0")
BLUE_LIGHT = get_color_from_hex("#90CAF9")
ACCENT = get_color_from_hex("#1A73E8")
DARK = get_color_from_hex("#222222")
GRAY = get_color_from_hex("#888888")
WHITE = get_color_from_hex("#FFFFFF")
BG = get_color_from_hex("#F5F6F8")

# ============================================================
# 主题系统（浅色 / 深色双模式）
# ============================================================

_PALETTES = {
    'light': dict(
        bg='#F2F4F8', card='#FFFFFF', card2='#F2F5FA', field='#FFFFFF',
        text='#1B2530', sub='#5E6B7C', hint='#98A2B3',
        primary='#165DFF', primary_deep='#0E42D2', primary_soft='#E8EFFF',
        border='#E4E7EC', tab_bg='#FFFFFF',
        hot='#D93025', hot_soft='#FDECEA', cold='#667085', cold_soft='#EDF0F4',
        blue='#1650D8', blue_soft='#E3EDFF', win='#0C9A6C', win_soft='#E5F6EF',
        warn='#F2A93B', violet='#7C5CFF', cyan='#12B5CB',
        shadow=(0.07, 0.10, 0.17),
    ),
    'dark': dict(
        bg='#12151C', card='#1C2230', card2='#242C3D', field='#1A2030',
        text='#E8ECF3', sub='#A5AEBD', hint='#6B7484',
        primary='#4D7EFF', primary_deep='#3B66E0', primary_soft='#22304F',
        border='#2A3345', tab_bg='#1C2230',
        hot='#FF6B5E', hot_soft='#3A2320', cold='#8A93A5', cold_soft='#262E3F',
        blue='#7CA0FF', blue_soft='#22304F', win='#2FC08A', win_soft='#173229',
        warn='#F2A93B', violet='#9B85FF', cyan='#2BC8D8',
        shadow=(0.0, 0.0, 0.0),
    ),
}

class _Theme:
    mode = 'light'
    @classmethod
    def c(cls, key):
        return get_color_from_hex(_PALETTES[cls.mode][key])
    @classmethod
    def toggle(cls):
        cls.mode = 'dark' if cls.mode == 'light' else 'light'

def C(key):
    """取当前主题颜色"""
    return _Theme.c(key)

def C_HEX(key):
    return _PALETTES[_Theme.mode][key]

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
    mx = max(d.values()) if d else 0
    if mx <= 0:
        return {k: 0.0 for k in d}
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
        # 仅在缓存为空、或差口不大时才联网拉取（n=100000 表示"全部缓存"，不应触发联网）
        if not rows or (len(rows) < n and n <= 1000):
            try:
                rows = self.fetch_all()
                self.save_cache(rows)
            except Exception as e:
                print(f"[警告]联网失败: {e}")
                if not rows: rows = self.load_cache()
        if n >= len(rows): return rows
        return rows[-n:]

    def next_code(self):
        """推荐期号 = 历史最新期号 + 1（开奖前=当期；开奖后/非开奖日=下一期）"""
        try:
            rows = self.get_data(1)
            return str(int(rows[-1]["code"]) + 1) if rows else ""
        except Exception:
            return ""

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


def check_constraints(reds, **overrides):
    _sum = overrides.get('sum_range', SUM_RANGE)
    _odd = overrides.get('odd_range', ODD_RANGE)
    _big = overrides.get('big_range', BIG_RANGE)
    _span = overrides.get('span_range', SPAN_RANGE)
    _consec = overrides.get('max_consec', MAX_CONSEC)
    _zone = overrides.get('zone_max', ZONE_MAX_IN_ONE)
    s = sorted(reds)
    if not (_sum[0] <= sum(s) <= _sum[1]): return False
    if not (_odd[0] <= sum(1 for x in s if x % 2) <= _odd[1]): return False
    if not (_big[0] <= sum(1 for x in s if x >= 18) <= _big[1]): return False
    if not (_span[0] <= s[-1] - s[0] <= _span[1]): return False
    run = mx = 1
    for a, b in zip(s, s[1:]): run = run + 1 if b - a == 1 else 1; mx = max(mx, run)
    if mx > _consec: return False
    if max(Counter((x - 1) // 11 for x in s).values()) > _zone: return False
    return True


def draw_weighted(scores, k, tries=2000, **constraints):
    nums = list(scores.keys()); weights = [scores[x] + 1e-6 for x in nums]
    for _ in range(tries):
        picked = sorted(random.choices(nums, weights=weights, k=k))
        if len(set(picked)) == k and check_constraints(picked, **constraints): return picked
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

class KivyBarChart(Widget):
    """用 Kivy canvas 绘制的柱状图控件。
    data: dict {label: value}
    title: 图标题
    color: 柱体颜色 (r,g,b,a) 默认蓝
    labels: 可选 dict 映射 label 显示文本
    backtest: bool，双柱对比图（回测用）
    """
    def __init__(self, data, title='', color=(0.20, 0.60, 0.86, 1), labels=None, backtest=False, **kw):
        super().__init__(**kw)
        self.data = data
        self.chart_title = title
        self.bar_color = color
        self.label_map = labels or {}
        self.backtest = backtest
        self.size_hint_y = None
        self.height = '240dp'
        # 强制在布局完成后重画（解决首次 on_size 时 width=0 画空帧的问题）
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self.on_size(), 0.2)

    def on_size(self, *a):
        if self.width <= 1 or self.height <= 1:
            return
        self.canvas.clear()
        self._draw()

    def _draw(self):
        w = self.width
        try:
            h = float(self.height)
        except Exception:
            h = 200.0
        # 限制绘制基准高度，防止柱子异常高覆盖下方内容
        if h > 280:
            h = 280
        if w <= 1 or h <= 5:
            return
        from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
        chart_w = w        # 占满宽度
        chart_h = h - 32   # 底部留 32 画轴标签
        if chart_h < 10:
            chart_h = 10

        # 白色底
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=(0, 0), size=(w, h))

        # 标题（深色，居中顶部）
        if self.chart_title:
            from kivy.core.text import Label as CoreLabel
            c = CoreLabel(text=self.chart_title, font_size=15, bold=True, color=(0.17, 0.24, 0.31, 1))
            c.refresh()
            tex = c.texture
            with self.canvas:
                Color(0.17, 0.24, 0.31, 1)
                Rectangle(texture=tex, pos=(w / 2 - tex.width / 2, h - tex.height * 1.1),
                          size=(tex.width, tex.height))

        top_margin = 30 if self.chart_title else 10
        base_y = 4
        draw_h = chart_h - top_margin
        if draw_h < 10:
            draw_h = 10
        if self.backtest:
            self._draw_backtest(w, draw_h, top_margin, base_y)
        else:
            self._draw_bars(w, draw_h, top_margin, base_y)

    def _draw_bars(self, chart_w, chart_h, top_margin):
        from kivy.graphics import Color, Rectangle, RoundedRectangle
    def _draw_bars(self, chart_w, chart_h, top_margin, base_y=4):
        from kivy.graphics import Color, Rectangle, RoundedRectangle
        from kivy.core.text import Label as CoreLabel
        items = sorted(self.data.keys())
        if not items:
            return
        vals = [self.data[k] for k in items]
        vmax = max(vals) if vals else 1
        if vmax <= 0:
            vmax = 1
        n = len(items)
        gap = 3
        bw = (chart_w - gap * (n + 1)) / n
        for i, k in enumerate(items):
            lab = self.label_map.get(str(k), str(k))
            v = self.data[k]
            bh = (v / vmax) * chart_h
            x = gap + i * (bw + gap)
            with self.canvas:
                Color(*self.bar_color)
                RoundedRectangle(pos=(x, base_y), size=(bw, max(2, bh)), radius=[2])
            # 轴标签（柱下方，加大字号防重叠）
            c = CoreLabel(text=lab, font_size=11, color=(0.35, 0.35, 0.35, 1))
            c.refresh(); tex = c.texture
            with self.canvas:
                Color(0.35, 0.35, 0.35, 1)
                Rectangle(texture=tex, pos=(x + bw / 2 - tex.width / 2, base_y - tex.height * 1.1),
                          size=(tex.width, tex.height))

    def _draw_backtest(self, chart_w, chart_h, top_margin, base_y=4):
        from kivy.graphics import Color, Rectangle, RoundedRectangle
        from kivy.core.text import Label as CoreLabel
        names = ['未中', '六等', '五等', '四等', '三等', '二等', '一等']
        sg = self.data.get('strat', {})
        rg = self.data.get('rand', {})
        sx = [sg.get(i, 0) for i in range(7)]
        rx = [rg.get(i, 0) for i in range(7)]
        vmax = max(max(sx), max(rx), 1)
        if vmax <= 0:
            vmax = 1
        n = 7
        gap = 2
        bw = (chart_w - gap * (n + 1)) / n
        half = bw / 2
        for i in range(n):
            lab = names[i]
            x = gap + i * (bw + gap)
            bh1 = (sx[i] / vmax) * chart_h
            bh2 = (rx[i] / vmax) * chart_h
            with self.canvas:
                Color(0.93, 0.30, 0.24, 1)
                RoundedRectangle(pos=(x + 1, base_y), size=(half - 1, max(2, bh1)), radius=[2])
                Color(0.20, 0.60, 0.86, 1)
                RoundedRectangle(pos=(x + half, base_y), size=(half - 1, max(2, bh2)), radius=[2])
            c = CoreLabel(text=lab, font_size=9, color=(0.4, 0.4, 0.4, 1))
            c.refresh(); tex = c.texture
            with self.canvas:
                Color(0.4, 0.4, 0.4, 1)
                Rectangle(texture=tex, pos=(x + bw / 2 - tex.width / 2, base_y - tex.height * 1.2),
                          size=(tex.width, tex.height))



def _lbl(text='', fs=13, color_key='text', bold=False, halign='left', valign='middle',
         h=None, width=None, size_hint_x=None):
    """通用 Label：自动绑定 text_size（支持 halign/valign）"""
    lbl = Label(text=str(text), font_size=dp(fs), bold=bold, color=C(color_key),
                size_hint_y=None, halign=halign, valign=valign)
    if h:
        lbl.height = dp(h) if isinstance(h, (int, float)) else h
    if width is not None:
        lbl.size_hint_x = None
        lbl.width = dp(width) if isinstance(width, (int, float)) else width
    if size_hint_x is not None:
        lbl.size_hint_x = size_hint_x
    lbl.bind(size=lambda o, v: setattr(o, 'text_size', (o.width, o.height or None)))
    lbl.text_size = (lbl.width, lbl.height or None)
    return lbl


def _bg(w, fill, radius=14, border=None, shadow=False):
    """给 widget 画圆角背景（可选描边/柔和阴影），并绑定跟随位置尺寸"""
    sh = _PALETTES[_Theme.mode]['shadow']
    has_shadow = shadow and (sh[0] or sh[1] or sh[2])
    radius = dp(radius) if isinstance(radius, (int, float)) else radius
    with w.canvas.before:
        if has_shadow:
            for dy, spread, a in ((dp(1), dp(5), 0.05), (dp(3), dp(10), 0.03)):
                Color(sh[0], sh[1], sh[2], a)
                RoundedRectangle(pos=(w.x - spread / 2, w.y - dy),
                                 size=(w.width + spread, w.height + spread),
                                 radius=[radius + dp(3)])
        Color(*fill)
        w._bg_rect = RoundedRectangle(pos=w.pos, size=w.size, radius=[radius])
        if border is not None:
            Color(*border)
            w._bg_border = Line(rounded_rectangle=(w.x, w.y, w.width, w.height, radius), width=1)

    def _sync(o, v):
        o._bg_rect.pos = o.pos
        o._bg_rect.size = o.size
        if border is not None:
            o._bg_border.rounded_rectangle = (o.x, o.y, o.width, o.height, radius)
    w.bind(pos=_sync, size=_sync)
    return w


def Card(*children, **kw):
    """卡片：圆角 + 柔和阴影 + 自适应内容高度"""
    pad = kw.get('padding', dp(12))
    sp = kw.get('spacing', dp(8))
    radius = kw.get('radius', 14)
    fill = kw.get('fill') or C('card')
    box = BoxLayout(orientation='vertical', size_hint_y=None, padding=pad, spacing=sp)
    box.bind(minimum_height=lambda o, v: setattr(o, 'height', v + pad * 2))
    _bg(box, fill, radius=radius, shadow=kw.get('shadow', True))
    for ch in children:
        box.add_widget(ch)
    return box


_CAP_STYLES = {'red': ('hot_soft', 'hot'), 'blue': ('blue_soft', 'blue'),
               'cold': ('cold_soft', 'cold'), 'dim': ('card2', 'sub'),
               'win': ('win_soft', 'win'), 'primary': ('primary_soft', 'primary')}


def Capsule(text, kind='red', w=None, h=None, fs=None, bold=True):
    """圆角胶囊号码标签（现代样式，浅底深字）"""
    h = h or dp(30)
    w = w or dp(40)
    bgl, fgl = _CAP_STYLES.get(kind, _CAP_STYLES['dim'])
    lbl = Label(text=str(text), font_size=fs or dp(12), bold=bold, color=C(fgl),
                size_hint=(None, None), size=(w, h), halign='center', valign='middle')
    lbl.text_size = (w, h)
    _bg(lbl, C(bgl), radius=h / 2)
    return lbl


def _ball_label(text, color, bg, size='48dp'):
    """兼容旧签名：转调 Capsule"""
    try:
        d = int(str(size).replace('dp', ''))
    except Exception:
        d = 40
    if bg == BLUE:
        kind = 'blue'
    elif bg == RED:
        kind = 'red'
    else:
        kind = 'cold'
    return Capsule(text, kind, w=dp(d), h=dp(int(d * 0.8)), fs=dp(12) if d < 36 else dp(14))


def SectionTitle(text, right=None):
    """区块标题：主色竖条 + 加粗文字（可附右侧组件）"""
    row = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(8))
    bar = Widget(size_hint=(None, 1), width=dp(4))
    _bg(bar, C('primary'), radius=dp(2))
    row.add_widget(bar)
    lbl = _lbl(text, 15, 'text', bold=True, h=26, size_hint_x=1)
    row.add_widget(lbl)
    if right is not None:
        row.add_widget(right)
    return row


def _title_row(text):
    """兼容旧签名"""
    return SectionTitle(text)


def Hint(text, h=None):
    """辅助说明小字：高度随内容自适应（多行不溢出）"""
    lbl = Label(text=str(text), font_size=dp(11), color=C('sub'),
                size_hint_y=None, halign='left', valign='middle')
    lbl.bind(width=lambda o, v: setattr(o, 'text_size', (v, None)))
    lbl.bind(texture_size=lambda o, v: setattr(o, 'height', max(v[1], dp(16))))
    lbl.height = dp(16)
    return lbl


def _hint(text):
    """兼容旧签名"""
    return Hint(text)


def _row(*widgets, **kw):
    h = kw.get('height', '40dp')
    box = BoxLayout(size_hint_y=None, height=h, spacing=dp(8), **{k: v for k, v in kw.items() if k != 'height'})
    for w in widgets:
        box.add_widget(w)
    return box


def PButton(text, kind='primary', h=46, fs=14, on_press=None, pill=False, **kw):
    """现代圆角按钮：primary 主色 / soft 浅底 / ghost 描边 / danger 红调"""
    h = dp(h) if isinstance(h, (int, float)) else h
    styles = {
        'primary': (C('primary'), (1, 1, 1, 1), None),
        'soft': (C('primary_soft'), C('primary'), None),
        'ghost': ((0, 0, 0, 0), C('sub'), C('border')),
        'danger': (C('hot_soft'), C('hot'), None),
        'win': (C('win_soft'), C('win'), None),
    }
    fill, fg, border = styles.get(kind, styles['primary'])
    b = Button(text=str(text), font_size=dp(fs), size_hint_y=None, height=h,
               background_color=(0, 0, 0, 0), color=fg, bold=(kind == 'primary'),
               disabled_color=fg, **kw)
    _bg(b, fill, radius=(h / 2 if pill else dp(12)),
        border=border if border is not None else None)
    if on_press:
        b.bind(on_press=on_press)
    return b


def TInput(hint='', text='', h=40, **kw):
    """圆角输入框（聚焦主色描边）"""
    hpx = dp(h) if isinstance(h, (int, float)) else h
    ti = TextInput(hint_text=hint, text=text, multiline=False, size_hint_y=None, height=hpx,
                   font_size=dp(13), background_normal='', background_disabled_normal='',
                   background_active='', background_color=(0, 0, 0, 0),
                   foreground_color=C('text'), cursor_color=C('primary'),
                   hint_text_color=C('hint'), padding=[dp(10), (hpx - dp(16)) / 2, dp(10), 0],
                   write_tab=False, **kw)

    def _draw(focused=False):
        ti.canvas.before.clear()
        with ti.canvas.before:
            Color(*C('field'))
            RoundedRectangle(pos=ti.pos, size=ti.size, radius=[dp(10)])
            Color(*(C('primary') if focused else C('border')))
            Line(rounded_rectangle=(ti.x, ti.y, ti.width, ti.height, dp(10)), width=1)

    def _sync(o, v):
        _draw(getattr(o, '_focused', False))
    ti._focused = False
    ti.bind(pos=_sync, size=_sync)
    ti.bind(focus=lambda o, v: (setattr(o, '_focused', v), _draw(v)))
    _draw()
    return ti


class _TOption(SpinnerOption):
    """Spinner 下拉选项（主题化）"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)
        self.height = dp(42)
        self.font_size = dp(13)
        self.color = C('text')
        _bg(self, C('card'), radius=dp(10), border=C('border'))


class TSpinner(Spinner):
    """圆角 Spinner（下拉浮层主题化）"""

    def __init__(self, values=(), text='', **kw):
        super().__init__(text=text, values=list(values), **kw)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)
        self.font_size = dp(13)
        self.color = C('text')
        self.bold = False
        self.option_cls = _TOption
        _bg(self, C('field'), radius=dp(10), border=C('border'))

    def _toggle_dropdown(self, *largs):
        had = self.dropdown
        super()._toggle_dropdown(*largs)
        dd = self.dropdown
        if dd is not None and dd is not had:

            def _paint(o=None, v=None):
                dd.canvas.clear()
                with dd.canvas.before:
                    Color(*C('card'))
                    RoundedRectangle(pos=dd.pos, size=dd.size, radius=[dp(10)])
                    Color(*C('border'))
                    Line(rounded_rectangle=(dd.x, dd.y, dd.width, dd.height, dp(10)), width=1)
            _paint()
            dd.bind(pos=_paint, size=_paint)


class SoftSlider(Widget):
    """自绘触控滑条：圆角轨道 + 主色填充 + 圆形手柄（手指友好）"""

    def __init__(self, value=0.5, vmin=0.0, vmax=1.0, on_change=None, fill_key='primary', **kw):
        super().__init__(**kw)
        self.size_hint_y = None
        self.height = dp(34)
        self._min = vmin
        self._max = vmax
        self.value = value
        self._cb = on_change
        self._fill = fill_key
        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(lambda *a: self._redraw(), 0)

    def _set_frac(self, frac):
        frac = max(0.0, min(1.0, frac))
        v = self._min + (self._max - self._min) * frac
        if abs(v - self.value) > 1e-6:
            self.value = v
            if self._cb:
                self._cb(v)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self._set_frac((touch.x - self.x - dp(10)) / max(dp(1), self.width - dp(20)))
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._set_frac((touch.x - self.x - dp(10)) / max(dp(1), self.width - dp(20)))
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def _redraw(self, *a):
        self.canvas.clear()
        cy = self.center_y
        x0 = self.x + dp(10)
        x1 = self.x + self.width - dp(10)
        if x1 <= x0:
            return
        frac = max(0.0, min(1.0, (self.value - self._min) / ((self._max - self._min) or 1)))
        with self.canvas:
            Color(*C('border'))
            RoundedRectangle(pos=(x0, cy - dp(2)), size=(x1 - x0, dp(4)), radius=[dp(2)])
            Color(*C(self._fill))
            RoundedRectangle(pos=(x0, cy - dp(2)), size=(max(dp(4), (x1 - x0) * frac), dp(4)),
                             radius=[dp(2)])
            hx = x0 + (x1 - x0) * frac
            Color(1, 1, 1, 1)
            Ellipse(pos=(hx - dp(9), cy - dp(9)), size=(dp(18), dp(18)))
            Color(*C(self._fill))
            Line(circle=(hx, cy, dp(8.5)), width=dp(1.6))


class MixBar(Widget):
    """权重占比条：四色分段，宽度与权重成正比"""

    _keys = ['primary', 'violet', 'cyan', 'warn']

    def __init__(self, **kw):
        super().__init__(**kw)
        self.size_hint_y = None
        self.height = dp(14)
        self._vals = [0.25, 0.25, 0.25, 0.25]
        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(lambda *a: self._redraw(), 0)

    def update(self, vals):
        self._vals = list(vals)
        self._redraw()

    def _redraw(self, *a):
        self.canvas.clear()
        tot = sum(self._vals) or 1
        x = self.x
        with self.canvas:
            for i, v in enumerate(self._vals):
                seg = self.width * v / tot
                Color(*C(self._keys[i % 4]))
                RoundedRectangle(pos=(x, self.y + dp(1)),
                                 size=(max(dp(2), seg - dp(1)), self.height - dp(2)),
                                 radius=[dp(2)])
                x += seg


class Icon(Widget):
    """自绘线性图标（无字体依赖）"""

    def __init__(self, name, size_dp=22, color=None, **kw):
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = (dp(size_dp), dp(size_dp))
        self._name = name
        self._col = color if color is not None else C('sub')
        self._lw = dp(1.6)
        self.bind(pos=self._redraw, size=self._redraw)
        Clock.schedule_once(lambda *a: self._redraw(), 0)

    def set_icon(self, name):
        self._name = name
        self._redraw()

    def _redraw(self, *a):
        self.canvas.clear()
        fn = getattr(self, '_ic_' + self._name, None)
        if fn:
            fn()

    def _ic_home(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        cx = x + w / 2
        ym = y + h * 0.44
        yt = y + h * 0.9
        yb = y + h * 0.1
        with self.canvas:
            Color(*self._col)
            Line(points=[x + w * 0.06, ym, cx, yt, x + w * 0.94, ym], width=self._lw)
            Line(rounded_rectangle=(x + w * 0.22, yb, w * 0.56, ym - yb, 2), width=self._lw)

    def _ic_chart(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            for i, hh in enumerate((0.4, 0.72, 1.0)):
                RoundedRectangle(pos=(x + w * (0.12 + i * 0.31), y + h * 0.08),
                                 size=(w * 0.2, (h - dp(2)) * hh * 0.9), radius=[dp(1.5)])

    def _ic_target(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2 - self._lw
        with self.canvas:
            Color(*self._col)
            Line(circle=(cx, cy, r * 0.95), width=self._lw)
            Line(circle=(cx, cy, r * 0.55), width=self._lw)
            Color(*self._col)
            Ellipse(pos=(cx - r * 0.14, cy - r * 0.14), size=(r * 0.28, r * 0.28))

    def _ic_loop(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2 - self._lw
        with self.canvas:
            Color(*self._col)
            Line(circle=(cx, cy, r, 25, 155), width=self._lw)
            Line(circle=(cx, cy, r, 205, 335), width=self._lw)
            Color(*self._col)
            Triangle(points=[cx + r * 0.92, cy + r * 0.42, cx + r * 0.62, cy + r * 0.30,
                             cx + r * 0.92, cy + r * 0.02])
            Triangle(points=[cx - r * 0.92, cy - r * 0.42, cx - r * 0.62, cy - r * 0.30,
                             cx - r * 0.92, cy - r * 0.02])

    def _ic_list(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            for i, fy in enumerate((0.78, 0.52, 0.26)):
                yy = y + h * fy
                Line(points=[x + w * 0.32, yy, x + w * 0.94, yy], width=self._lw)
                Ellipse(pos=(x + w * 0.06, yy - dp(1.6)), size=(dp(3.2), dp(3.2)))

    def _ic_copy(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            Line(rounded_rectangle=(x + w * 0.34, y + h * 0.06, w * 0.56, h * 0.56, dp(3)), width=self._lw)
            Line(rounded_rectangle=(x + w * 0.1, y + h * 0.32, w * 0.56, h * 0.56, dp(3)), width=self._lw)

    def _ic_trash(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            Line(points=[x + w * 0.14, y + h * 0.8, x + w * 0.86, y + h * 0.8], width=self._lw)
            Line(points=[x + w * 0.5, y + h * 0.8, x + w * 0.5, y + h * 0.92], width=self._lw)
            Line(rounded_rectangle=(x + w * 0.24, y + h * 0.08, w * 0.52, h * 0.66, dp(3)), width=self._lw)
            Line(points=[x + w * 0.42, y + h * 0.22, x + w * 0.42, y + h * 0.6], width=self._lw)
            Line(points=[x + w * 0.58, y + h * 0.22, x + w * 0.58, y + h * 0.6], width=self._lw)

    def _ic_sun(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2
        with self.canvas:
            Color(*self._col)
            Ellipse(pos=(cx - r * 0.32, cy - r * 0.32), size=(r * 0.64, r * 0.64))
            for i in range(8):
                ang = i * 3.14159265 / 4
                x1 = cx + (r * 0.52) * (1 if abs((i % 4) - 2) < 0.5 else 0.707) * (1 if i % 4 != 2 else 0)
                from math import cos, sin
                x1 = cx + (r * 0.55) * cos(ang)
                y1 = cy + (r * 0.55) * sin(ang)
                x2 = cx + (r * 0.85) * cos(ang)
                y2 = cy + (r * 0.85) * sin(ang)
                Line(points=[x1, y1, x2, y2], width=self._lw)

    def _ic_moon(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        cx, cy = x + w / 2, y + h / 2
        r = min(w, h) / 2 - self._lw
        with self.canvas:
            Color(*self._col)
            Line(circle=(cx, cy, r * 0.9, 55, 305), width=self._lw)
            Line(circle=(cx + r * 0.42, cy + r * 0.1, r * 0.72, 170, 375), width=self._lw)

    def _ic_chev_down(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            Line(points=[x + w * 0.22, y + h * 0.62, x + w * 0.5, y + h * 0.32,
                         x + w * 0.78, y + h * 0.62], width=self._lw)

    def _ic_chev_right(self):
        x, y, w, h = self.x, self.y, self.width, self.height
        with self.canvas:
            Color(*self._col)
            Line(points=[x + w * 0.36, y + h * 0.74, x + w * 0.66, y + h * 0.5,
                         x + w * 0.36, y + h * 0.26], width=self._lw)


def IconBtn(name, on_press=None, d=38, fill=None, icon_color=None, icon_size=None):
    """圆形图标按钮"""
    dpx = dp(d) if isinstance(d, (int, float)) else d
    b = Button(size_hint=(None, None), size=(dpx, dpx), background_color=(0, 0, 0, 0))
    _bg(b, fill if fill is not None else C('card2'), radius=int(dpx / 2))
    ic = Icon(name, size_dp=icon_size or int(dpx / dp(1) * 0.52),
              color=icon_color or C('sub'))
    b.add_widget(ic)
    if on_press:
        b.bind(on_press=on_press)
    return b


def Toast(msg):
    """底部浮出提示条，1.5 秒后淡出"""
    wpx = min(dp(13) * len(str(msg)) + dp(44), Window.width - dp(48))
    lbl = Label(text=str(msg), font_size=dp(12), color=(1, 1, 1, 1), size_hint=(None, None),
                size=(wpx, dp(38)), halign='center', valign='middle')
    lbl.text_size = lbl.size
    _bg(lbl, (0.10, 0.12, 0.16, 0.93), radius=dp(19))
    lbl.pos = ((Window.width - wpx) / 2, dp(96))
    Window.add_widget(lbl)
    anim = Animation(opacity=0, d=1.2, t='in_quad')
    anim.bind(on_complete=lambda *a: Window.remove_widget(lbl))
    Clock.schedule_once(lambda *a: anim.start(lbl), 1.0)
    return lbl


class FoldPanel(BoxLayout):
    """可折叠面板卡片：点击标题展开/收起"""

    def __init__(self, title, builder, open=False, **kw):
        super().__init__(orientation='vertical', size_hint_y=None, **kw)
        self._open = bool(open)
        self._min_h = 0
        box = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(12), spacing=dp(8))
        box.bind(minimum_height=lambda o, v: setattr(o, 'height', v + dp(24)))
        _bg(box, C('card'), radius=dp(14), shadow=True)
        head = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(30), spacing=dp(6))
        head.add_widget(SectionTitle(title, bare=True) if False else _lbl(title, 15, 'text', bold=True, h=26, size_hint_x=1))
        self.chev = Icon('chev_down' if self._open else 'chev_right', size_dp=18, color=C('sub'))
        head.add_widget(Widget())
        head.add_widget(self.chev)
        head_btn = Button(size_hint=(1, 1), background_color=(0, 0, 0, 0))
        head_btn.bind(on_press=self.toggle)
        head.add_widget(head_btn)
        box.add_widget(head)
        self.body = BoxLayout(orientation='vertical', size_hint_y=None, height=0, spacing=dp(8))
        self.body.bind(minimum_height=self._on_min)
        builder(self.body)
        box.add_widget(self.body)
        self.add_widget(box)
        Clock.schedule_once(lambda *a: self._apply(instant=True), 0)

    def _on_min(self, o, v):
        self._min_h = v
        if self._open and abs(self.body.height - v) > 0.5:
            self.body.height = v

    def _apply(self, instant=False):
        target = self._min_h if self._open else 0
        self.body.opacity = 1 if self._open else 0
        if instant:
            self.body.height = target
            self.body.opacity = 1 if self._open else 0
        else:
            Animation(height=target, d=0.18, t='out_quad').start(self.body)
            Animation(opacity=1 if self._open else 0, d=0.15).start(self.body)

    def toggle(self, *a):
        self._open = not self._open
        self.chev.set_icon('chev_down' if self._open else 'chev_right')
        self._apply()


def _hbar_row(lab, ratio, color, val_text='', lab_w=36):
    """单行水平条形：标签 + 彩色条 + 数值（条宽显式 dp，比例确定）"""
    row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(20), spacing=dp(4))
    row.add_widget(_lbl(str(lab), 10, 'sub', h=18, width=lab_w))
    bar_w = int(10 + 240 * max(0.0, min(1.0, ratio)))
    bar = Widget(size_hint_x=None, width=dp(bar_w), size_hint_y=None, height=dp(14))
    with bar.canvas.before:
        Color(*color)
        bar.bg = RoundedRectangle(pos=bar.pos, size=bar.size, radius=[dp(3)])
    bar.bind(pos=lambda *a, b=bar: setattr(b.bg, 'pos', a[1]),
             size=lambda *a, b=bar: setattr(b.bg, 'size', a[1]))
    row.add_widget(bar)
    if val_text:
        row.add_widget(_lbl(val_text, 9, 'hint', h=18, width=44))
    return row


def _bar_chart(data, title='', color=None, labels=None):
    """基于 Widget+背景色 的水平条形图，按比例自动占满屏宽"""
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(3))
    box.bind(minimum_height=box.setter('height'))
    if title:
        box.add_widget(SectionTitle(title))
    for i, (k, v) in enumerate(data.items()):
        mx = max(data.values()) or 1
        ratio = v / mx
        val = labels[i] if (labels and i < len(labels)) else f"{v:.0f}"
        box.add_widget(_hbar_row(k, ratio, color if color is not None else C('primary'), val))
    return box


def chart_freq(freq):
    return _bar_chart(freq, "红球出现频率", C('hot'))


def chart_omit(omit):
    return _bar_chart(omit, "红球遗漏值", C('hot'))


def chart_score(scores):
    return _bar_chart(scores, "红球综合评分", C('hot'))


def chart_tail_freq(tails):
    return _bar_chart(tails, "尾数频率", C('violet'))


def chart_zone_freq(zones):
    z_names = {0: "一区(01-11)", 1: "二区(12-22)", 2: "三区(23-33)"}
    return _bar_chart(zones, "区间出号", C('cyan'), labels=z_names)


def chart_blue_freq(freq):
    return _bar_chart(freq, "蓝球出现频率", C('blue'))


def chart_backtest(strat_g, rand_g):
    """回测对比：每奖级双条（策略=主蓝 / 随机=灰蓝）"""
    box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(3))
    box.bind(minimum_height=box.setter('height'))
    box.add_widget(SectionTitle("策略 vs 随机（各奖级注数）"))
    legend = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(18), spacing=dp(12))
    _seg = BoxLayout(size_hint_x=None, width=dp(12), size_hint_y=None, height=dp(10))
    with _seg.canvas.before:
        Color(*C('primary'))
        _seg.bg = RoundedRectangle(pos=_seg.pos, size=_seg.size, radius=[dp(2)])
    _seg.bind(pos=lambda *a: setattr(_seg.bg, 'pos', a[1]), size=lambda *a: setattr(_seg.bg, 'size', a[1]))
    lg1 = BoxLayout(size_hint_x=None, width=dp(64), spacing=dp(4))
    lg1.add_widget(_seg)
    lg1.add_widget(_lbl("策略", 9, 'text', h=16))
    _seg2 = BoxLayout(size_hint_x=None, width=dp(12), size_hint_y=None, height=dp(10))
    with _seg2.canvas.before:
        Color(*C('cold'))
        _seg2.bg = RoundedRectangle(pos=_seg2.pos, size=_seg2.size, radius=[dp(2)])
    _seg2.bind(pos=lambda *a: setattr(_seg2.bg, 'pos', a[1]), size=lambda *a: setattr(_seg2.bg, 'size', a[1]))
    lg2 = BoxLayout(size_hint_x=None, width=dp(64), spacing=dp(4))
    lg2.add_widget(_seg2)
    lg2.add_widget(_lbl("随机", 9, 'text', h=16))
    legend.add_widget(lg1)
    legend.add_widget(lg2)
    box.add_widget(legend)
    names = ['未中', '六等', '五等', '四等', '三等', '二等', '一等']
    for i, nm in enumerate(names):
        s = strat_g.get(i, 0)
        r = rand_g.get(i, 0)
        tot = s + r
        if tot <= 0:
            continue
        row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(22), spacing=dp(4))
        row.add_widget(_lbl(nm, 10, 'sub', h=18, width=34))
        b1 = Widget(size_hint_x=max(s / tot, 0.02), size_hint_y=None, height=dp(15))
        with b1.canvas.before:
            Color(*C('primary'))
            b1.bg = RoundedRectangle(pos=b1.pos, size=b1.size, radius=[dp(3)])
        b1.bind(pos=lambda *a, b=b1: setattr(b.bg, 'pos', a[1]), size=lambda *a, b=b1: setattr(b.bg, 'size', a[1]))
        row.add_widget(b1)
        b2 = Widget(size_hint_x=max(r / tot, 0.02), size_hint_y=None, height=dp(15))
        with b2.canvas.before:
            Color(*C('cold'))
            b2.bg = RoundedRectangle(pos=b2.pos, size=b2.size, radius=[dp(3)])
        b2.bind(pos=lambda *a, b=b2: setattr(b.bg, 'pos', a[1]), size=lambda *a, b=b2: setattr(b.bg, 'size', a[1]))
        row.add_widget(b2)
        box.add_widget(row)
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
        self.content.bind(minimum_height=lambda o, v: setattr(o, 'height', v + 24))
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
            line = BoxLayout(size_hint_y=None, height='52dp', spacing=8)
            for x in r["red"]: line.add_widget(_ball_label(f"{x:02d}", 1, RED, '40dp'))
            line.add_widget(_ball_label(f"{r['blue']:02d}", 1, BLUE, '40dp'))
            self.content.add_widget(line)
            pz = r.get('prizes', {})
            def _pz(t):
                d = pz.get(str(t), {})
                return f"{d.get('count', 0)}注/每注{(d.get('money', 0) or 0)//10000}万"
            info = Label(text=(f"第 {r['code']} 期  {r['date']} {r.get('week', '')}  销售额: {r.get('sales', 0)//10000}万  奖池: {r.get('poolmoney', 0)//10000}万\n"
                               f"一等奖 {_pz(1)}   二等奖 {_pz(2)}   三等奖 {_pz(3)}"),
                         size_hint_y=None, height='60dp', color=DARK, font_size='11sp')
            self.content.add_widget(info)
        else:
            self.content.add_widget(Label(text="暂无数据", color=GRAY, size_hint_y=None, height='40dp'))

        self.content.add_widget(_title_row("热号 / 冷号"))
        self.content.add_widget(_hint("热号=近100期红球出现次数最多的前10个；冷号=出现次数最少的前10个（两表互不重复）。蓝球同理。"))
        rows = self.dm.get_data(100)
        freq = frequency(rows, "red")
        hot = sorted(range(1, RED_COUNT + 1), key=lambda i: -freq[i])[:10]
        cold = sorted(range(1, RED_COUNT + 1), key=lambda i: freq[i])[:10]
        bfreq = frequency(rows, "blue")
        bhot = sorted(range(1, BLUE_COUNT + 1), key=lambda i: -bfreq[i])[:5]
        bcold = sorted(range(1, BLUE_COUNT + 1), key=lambda i: bfreq[i])[:5]

        self.content.add_widget(_hint("红球热号（出现最多）"))
        hbox = GridLayout(cols=6, size_hint_y=None, height='96dp', spacing=3)
        for x in hot: hbox.add_widget(_ball_label(f"{x:02d}", 1, RED, '36dp'))
        self.content.add_widget(hbox)

        self.content.add_widget(_hint("红球冷号（出现最少）"))
        hbox2 = GridLayout(cols=6, size_hint_y=None, height='96dp', spacing=3)
        for x in cold: hbox2.add_widget(_ball_label(f"{x:02d}", 1, (0.5, 0.5, 0.5, 1), '36dp'))
        self.content.add_widget(hbox2)

        self.content.add_widget(_hint("蓝球热号（左5，蓝）/ 冷号（右5，灰）"))
        bline = GridLayout(cols=10, size_hint_y=None, height='40dp', spacing=3)
        for x in bhot: bline.add_widget(_ball_label(f"{x:02d}", 1, BLUE, '30dp'))
        for x in bcold: bline.add_widget(_ball_label(f"{x:02d}", 1, (0.5, 0.5, 0.5, 1), '30dp'))
        self.content.add_widget(bline)

        # 历史开奖（从分析页移入概览，图表仅在分析页展示）
        self.content.add_widget(_title_row("历史开奖"))
        allrows = self.dm.get_data(100000)
        shown = allrows[-min(15, len(allrows)):]
        hist = BoxLayout(orientation='vertical', size_hint_y=None,
                         height=len(shown) * 36 + 10, spacing=2)
        hist.bind(minimum_height=hist.setter('height'))
        for hr in reversed(shown):
            hline = BoxLayout(size_hint_y=None, height='34dp', spacing=3)
            hline.add_widget(Label(text=f"{hr['code']}", size_hint_x=None, width='70dp',
                                    height='30dp', font_size='9sp', color=DARK))
            for x in hr["red"]: hline.add_widget(_ball_label(f"{x:02d}", 0.8, RED, '26dp'))
            hline.add_widget(_ball_label(f"{hr['blue']:02d}", 0.8, BLUE, '26dp'))
            hist.add_widget(hline)
        self.content.add_widget(hist)

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
        self.content.bind(minimum_height=lambda o, v: setattr(o, 'height', v + 24))
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

        score_grid = GridLayout(cols=8, size_hint_y=None, height='250dp', spacing=3)
        for i in range(1, RED_COUNT + 1):
            v = red_sc[i]
            mx = max(red_sc.values())
            ratio = v / mx if mx else 0
            r = int(ratio * 231)
            g = int((1 - ratio) * 52)
            b = 0
            lbl = Label(text=f"{i:02d}\n{v:.2f}", font_size='11sp', color=(1, 1, 1, 1),
                        size_hint=(None, None), size=('40dp', '42dp'), halign='center', valign='middle')
            with lbl.canvas.before:
                Color(r / 255, g / 255, b, 1)
                lbl.bg_r = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[4])
            lbl.bind(pos=lambda *a, l=lbl: setattr(l.bg_r, 'pos', a[1]),
                     size=lambda *a, l=lbl: setattr(l.bg_r, 'size', a[1]))
            score_grid.add_widget(lbl)
        self.content.add_widget(score_grid)

        self.content.add_widget(_title_row("蓝球评分"))
        bline = GridLayout(cols=8, size_hint_y=None, height='110dp', spacing=3)
        for i in range(1, BLUE_COUNT + 1):
            v = bsc[i]
            mx = max(bsc.values())
            ratio = v / mx if mx else 0
            g = int((1 - ratio) * 150)
            lbl = Label(text=f"{i:02d}\n{v:.2f}", font_size='11sp', color=(1, 1, 1, 1),
                        size_hint=(None, None), size=('40dp', '42dp'), halign='center', valign='middle')
            with lbl.canvas.before:
                Color(0.2, g / 255, 0.9, 1)
                lbl.bg_b = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[4])
            lbl.bind(pos=lambda *a, l=lbl: setattr(l.bg_b, 'pos', a[1]),
                     size=lambda *a, l=lbl: setattr(l.bg_b, 'size', a[1]))
            bline.add_widget(lbl)
        self.content.add_widget(bline)

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
            if p:
                self.content.add_widget(p)

        # 最新开奖
        self.content.add_widget(_title_row("历史开奖"))
        shown = rows[-min(20, len(rows)):]
        hist_grid = BoxLayout(orientation='vertical', size_hint_y=None,
                              height=len(shown) * 36 + 10, spacing=2)
        hist_grid.bind(minimum_height=hist_grid.setter('height'))
        for r in reversed(shown):
            line = BoxLayout(size_hint_y=None, height='34dp', spacing=3)
            line.add_widget(Label(text=f"{r['code']}", size_hint_x=None, width="70dp", height='30dp', font_size='9sp', color=DARK))
            for x in r["red"]: line.add_widget(_ball_label(f"{x:02d}", 0.8, RED, '26dp'))
            line.add_widget(_ball_label(f"{r['blue']:02d}", 0.8, BLUE, '26dp'))
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
        self.content.bind(minimum_height=lambda o, v: setattr(o, 'height', v + 24))
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
        self.content.add_widget(_hint("四项权重建议 0.3/0.35/0.2/0.15（合计≈1），滑动可调，越接近 1 越均衡。"))
        w_grid = GridLayout(cols=2, size_hint_y=None, height='160dp', spacing=5)
        self.w_freq_s = Slider(min=0, max=1, value=W_FREQ, size_hint_x=0.7)
        self.w_freq_l = Label(text=f"频率: {W_FREQ}", size_hint_x=0.3, height='30dp', color=DARK)
        self.w_freq_s.bind(value=lambda *a: setattr(self.w_freq_l, 'text', f"频率: {a[1]:.2f}"))
        w_grid.add_widget(self.w_freq_l); w_grid.add_widget(self.w_freq_s)

        self.w_omit_s = Slider(min=0, max=1, value=W_OMIT, size_hint_x=0.7)
        self.w_omit_l = Label(text=f"遗漏: {W_OMIT}", size_hint_x=0.3, height='30dp', color=DARK)
        self.w_omit_s.bind(value=lambda *a: setattr(self.w_omit_l, 'text', f"遗漏: {a[1]:.2f}"))
        w_grid.add_widget(self.w_omit_l); w_grid.add_widget(self.w_omit_s)

        self.w_tail_s = Slider(min=0, max=1, value=W_TAIL, size_hint_x=0.7)
        self.w_tail_l = Label(text=f"尾数: {W_TAIL}", size_hint_x=0.3, height='30dp', color=DARK)
        self.w_tail_s.bind(value=lambda *a: setattr(self.w_tail_l, 'text', f"尾数: {a[1]:.2f}"))
        w_grid.add_widget(self.w_tail_l); w_grid.add_widget(self.w_tail_s)

        self.w_zone_s = Slider(min=0, max=1, value=W_ZONE, size_hint_x=0.7)
        self.w_zone_l = Label(text=f"区间: {W_ZONE}", size_hint_x=0.3, height='30dp', color=DARK)
        self.w_zone_s.bind(value=lambda *a: setattr(self.w_zone_l, 'text', f"区间: {a[1]:.2f}"))
        w_grid.add_widget(self.w_zone_l); w_grid.add_widget(self.w_zone_s)
        self.content.add_widget(w_grid)
        reset_btn = Button(text="权重恢复默认 (0.30/0.35/0.20/0.15)", size_hint_y=None, height='38dp',
                            background_color=BLUE, color=(1, 1, 1, 1), font_size='12sp')
        def _reset_w(*a):
            self.w_freq_s.value = W_FREQ
            self.w_omit_s.value = W_OMIT
            self.w_tail_s.value = W_TAIL
            self.w_zone_s.value = W_ZONE
            self.w_freq_l.text = f"频率: {W_FREQ}"
            self.w_omit_l.text = f"遗漏: {W_OMIT}"
            self.w_tail_l.text = f"尾数: {W_TAIL}"
            self.w_zone_l.text = f"区间: {W_ZONE}"
        reset_btn.bind(on_press=_reset_w)
        self.content.add_widget(reset_btn)

        self.content.add_widget(_title_row("约束条件"))
        self.content.add_widget(_hint("和值=6红球和；奇数=红球奇数个数；大号=≥18的个数；跨度=最大-最小；最长连号；单区最多号数(01-11/12-22/23-33区)。"))
        self.content.add_widget(_hint("建议值：和值 90-120（均值≈100）；奇数 2-4；大号 2-4；跨度 15-30；最长连号 ≤3；单区最多 ≤4。"))
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
        self.content.add_widget(_row(Label(text="注数:", height='40dp', color=DARK), self.tickets_spin,
                                      Label(text="期数:", height='40dp', color=DARK), self.n_spin))

        self.gen_btn = Button(text="开始选号", size_hint_y=None, height='50dp',
                               background_color=ACCENT, color=(1, 1, 1, 1), font_size='18sp')
        self.gen_btn.bind(on_press=self._generate)
        self.content.add_widget(self.gen_btn)

        self.result_box = BoxLayout(orientation='vertical', size_hint_y=None, height='10dp', spacing=5)
        self.result_box.bind(minimum_height=self.result_box.setter('height'))
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
                self._last_tickets = result
                self.result_box.clear_widgets()
                rec_code = self.dm.next_code()
                self.result_box.add_widget(_title_row(f"第 {rec_code} 期 · 生成 {len(result)} 注（可上下滚动）"))
                for i, t in enumerate(result):
                    line = BoxLayout(size_hint_y=None, height='40dp', spacing=4)
                    line.add_widget(Label(text=f"{i + 1:02d}", size_hint_x=None, width='36dp', size_hint_y=None,
                                          height='34dp', font_size='12sp', color=DARK))
                    for x in t["red"]: line.add_widget(_ball_label(f"{x:02d}", 0.9, RED, '28dp'))
                    line.add_widget(_ball_label(f"{t['blue']:02d}", 0.9, BLUE, '28dp'))
                    save_btn = Button(text="存", size_hint_x=None, width='44dp', size_hint_y=None,
                                      height='32dp', font_size='13sp', background_color=ACCENT, color=(1, 1, 1, 1))
                    save_btn.bind(on_press=lambda *a, tt=t: self._save_ticket(tt))
                    line.add_widget(save_btn)
                    self.result_box.add_widget(line)
                if result:
                    all_btn = Button(text=f"一键存入全部 {len(result)} 注到购彩记录", size_hint_y=None, height='46dp',
                                     background_color=BLUE, color=(1, 1, 1, 1), font_size='14sp')
                    all_btn.bind(on_press=self._save_all)
                    self.result_box.add_widget(all_btn)
                self.gen_btn.disabled = False
                self.gen_btn.text = "开始选号"
                self.scroll.scroll_to(self.result_box)

            _show()

        threading.Thread(target=_do, daemon=True).start()

    def _latest_code(self):
        """返回推荐期号（最新+1）与今天日期"""
        try:
            nxt = self.dm.next_code()
            return nxt, today_str()
        except Exception:
            return "", today_str()

    def _save_ticket(self, t):
        try:
            code, date = self._latest_code()
            self.dm.add_record(code, date, t["red"], t["blue"], 1, 2)
            self._toast("已存入购彩记录")
        except Exception as e:
            self._toast(f"保存失败: {e}")

    def _save_all(self, *a):
        tickets = getattr(self, '_last_tickets', [])
        if not tickets:
            self._toast("没有可保存的选号结果")
            return
        code, date = self._latest_code()
        n = 0
        for t in tickets:
            try:
                self.dm.add_record(code, date, t["red"], t["blue"], 1, 2)
                n += 1
            except Exception:
                pass
        self._toast(f"已存入 {n} 注到购彩记录")

    def _toast(self, msg):
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        pop = Popup(title="提示", content=Label(text=msg, halign="center"),
                    size_hint=(0.6, None), height='120dp')
        pop.open()


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
        self.content.bind(minimum_height=lambda o, v: setattr(o, 'height', v + 24))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self._build()

    def _build(self):
        self.content.clear_widgets()
        self.content.add_widget(_title_row("回测参数"))
        self.content.add_widget(_hint("训练窗口=每次用多少期历史计算评分；每期注数=每期机选几注；轮次=重复次数（越多越稳定）；数据期数=总共回看多少期。结果与纯随机对比，策略不提高中奖概率。"))
        g = GridLayout(cols=2, size_hint_y=None, height='200dp', spacing=8)
        g.add_widget(Label(text="训练窗口(期):", height='36dp', color=DARK)); self.train = TextInput(text="50", multiline=False, height='36dp')
        g.add_widget(Label(text="每期注数:", height='36dp', color=DARK)); self.k = TextInput(text="5", multiline=False, height='36dp')
        g.add_widget(Label(text="轮次:", height='36dp', color=DARK)); self.rounds = TextInput(text="10", multiline=False, height='36dp')
        g.add_widget(Label(text="数据期数:", height='36dp', color=DARK)); self.n = TextInput(text="200", multiline=False, height='36dp')
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
        self.bt_result.bind(minimum_height=self.bt_result.setter('height'))
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
                    if p:
                        self.bt_result.add_widget(p)
                except: pass

                self.bt_result.height = self.bt_result.minimum_height
                self.bt_btn.disabled = False
                self.bt_btn.text = "开始回测"
                self.scroll.scroll_to(self.bt_result)

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
        self.content.bind(minimum_height=lambda o, v: setattr(o, 'height', v + 24))
        self.scroll.add_widget(self.content)
        self.root.add_widget(self.scroll)
        self.add_widget(self.root)
        self.refresh()

    def on_enter(self, *a):
        # 每次切到记录页都刷新，保证实时更新
        self.refresh()

    def refresh(self):
        self.content.clear_widgets()
        self._show_stats()
        self._show_add_form()
        self._show_list()

    def _show_stats(self):
        rows = self.dm.get_data(100000)
        recs, stats = self.dm.check_records(rows)
        box = BoxLayout(orientation='vertical', size_hint_y=None, height='150dp', padding=5, spacing=2)
        box.add_widget(Label(text="统计", font_size='14sp', bold=True, size_hint_y=None, height='30dp'))
        box.add_widget(Label(text=f"总注数: {stats['count']}  待开奖: {stats['pending']}",
                              size_hint_y=None, height='24dp', font_size='11sp', color=DARK))
        net_str = f"净盈亏: {stats['net']:+.0f}元"
        box.add_widget(Label(text=f"投入: {stats['total_in']:.0f}元  中奖: {stats['total_win']:.0f}元  {net_str}",
                              size_hint_y=None, height='24dp', font_size='11sp',
                              color=ACCENT if stats['net'] >= 0 else RED))
        btn = Button(text="一键对奖（按最新开奖核对兑奖）", size_hint_y=None, height='40dp',
                      background_color=BLUE, color=(1, 1, 1, 1), font_size='13sp')
        btn.bind(on_press=lambda *a: self._do_check())
        box.add_widget(btn)
        self.content.add_widget(box)

    def _do_check(self):
        rows = self.dm.get_data(100000)
        recs, stats = self.dm.check_records(rows)
        win = sum(1 for r in recs if r.get('win_grade', 0) > 0)
        self._popup("对奖完成", f"共 {stats['count']} 注记录，\n已兑奖 {stats['total_win']:.0f} 元，\n中奖 {win} 注，待开奖 {stats['pending']} 注。")

    def _show_add_form(self):
        box = BoxLayout(orientation='vertical', size_hint_y=None, height='340dp', padding=5, spacing=4)
        box.add_widget(Label(text="添加记录", font_size='14sp', bold=True, size_hint_y=None, height='30dp'))

        self.add_code = TextInput(text=self.dm.next_code(), hint_text="期号（已预填推荐期号）", multiline=False, height='36dp', size_hint_x=1)
        self.add_date = TextInput(text=today_str(), hint_text="日期", multiline=False, height='36dp', size_hint_x=1)
        self.add_red = TextInput(hint_text="红球，空格分隔，如 03 08 12 18 25 30", multiline=False, height='36dp', size_hint_x=1)
        self.add_blue = TextInput(hint_text="蓝球，如 07", multiline=False, height='36dp', size_hint_x=1)

        mn_row = BoxLayout(orientation='horizontal', size_hint_y=None, height='36dp', spacing=4)
        self.add_mult = TextInput(text="1", hint_text="倍数", multiline=False, height='36dp', size_hint_x=0.3, input_filter='int')
        self.add_note = TextInput(hint_text="备注（选填）", multiline=False, height='36dp', size_hint_x=0.7)
        mn_row.add_widget(self.add_mult); mn_row.add_widget(self.add_note)

        for w in [self.add_code, self.add_date, self.add_red, self.add_blue]:
            box.add_widget(w)
        box.add_widget(mn_row)

        btn = Button(text="保存记录", size_hint_y=None, height='44dp',
                      background_color=ACCENT, color=(1, 1, 1, 1))
        btn.bind(on_press=self._save_record)
        box.add_widget(btn)
        self.content.add_widget(box)

    def _save_record(self, *args):
        try:
            code = self.add_code.text.strip() or self.dm.next_code()
            red_txt = self.add_red.text.strip()
            blue_txt = self.add_blue.text.strip()
            if not red_txt:
                self._popup("提示", "请先填写红球号码（6个，空格分隔）")
                return
            if not blue_txt:
                self._popup("提示", "请先填写蓝球号码（01-16）")
                return
            red = [int(x) for x in red_txt.split()]
            blue = int(blue_txt)
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
            card = BoxLayout(orientation='vertical', size_hint_y=None, height='64dp',
                              padding=5, spacing=2)
            with card.canvas.before:
                Color(1, 1, 1, 1)
                card.bg = RoundedRectangle(pos=card.pos, size=card.size, radius=[6])
            card.bind(pos=lambda *a, c=card: setattr(c.bg, 'pos', a[1]),
                      size=lambda *a, c=card: setattr(c.bg, 'size', a[1]))
            top = BoxLayout(size_hint_y=None, height='26dp', spacing=4)
            top.add_widget(Label(text=f"{rec.get('code', '?')} {rec.get('date', '')}",
                                  size_hint_x=0.32, height='24dp', font_size='10sp', color=DARK))
            st = rec.get('status', '未开奖')
            clr = ACCENT if '一' in st or '二' in st or '三' in st else (RED if '未中奖' in st else GRAY)
            top.add_widget(Label(text=st, size_hint_x=0.22, height='24dp', font_size='10sp', color=clr))
            top.add_widget(Label(text=f"{rec.get('win_amount', 0):.0f}元", size_hint_x=0.14, height='24dp',
                                  font_size='10sp', color=ACCENT if rec.get('win_amount', 0) > 0 else GRAY))
            cp_btn = Button(text="复制", size_hint_x=0.16, height='24dp', font_size='11sp',
                             background_color=ACCENT, color=(1, 1, 1, 1))
            def _copy_num(*a, rr=rec):
                from kivy.core.clipboard import Clipboard
                txt = ' '.join(f"{x:02d}" for x in rr.get('red', [])) + ' + ' + f"{rr.get('blue', 0):02d}"
                Clipboard.copy(txt)
                self._popup("复制成功", "已复制到剪贴板：\n" + txt)
            cp_btn.bind(on_press=_copy_num)
            top.add_widget(cp_btn)
            del_btn = Button(text="删除", size_hint_x=0.16, height='24dp', font_size='11sp',
                              background_color=(0.95, 0.95, 0.95, 1), color=(0.6, 0.6, 0.6, 1))
            rid = rec['id']
            del_btn.bind(on_press=lambda *a, r=rid: self._del_record(r))
            top.add_widget(del_btn)
            card.add_widget(top)
            balls = BoxLayout(size_hint_y=None, height='26dp', spacing=3)
            for x in rec.get("red", []): balls.add_widget(_ball_label(f"{x:02d}", 0.85, RED, '26dp'))
            balls.add_widget(_ball_label(f"{rec.get('blue', 0):02d}", 0.85, BLUE, '26dp'))
            rh = rec.get('red_hit', '?')
            bh = rec.get('blue_hit', '?')
            balls.add_widget(Label(text=f"红:{rh} 蓝:{bh}", size_hint_x=0.2, height='24dp', font_size='10sp', color=GRAY))
            card.add_widget(balls)
            self.content.add_widget(card)
        self.content.add_widget(Label(size_hint_y=None, height='110dp'))

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
                          color=DARK)
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
        # data dir: use Kivy's user_data_dir (cross-platform, works on Android/desktop)
        data_dir = self.user_data_dir
        try:
            Path(data_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

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
