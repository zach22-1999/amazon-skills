#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
亚马逊 Brand Analytics 热门搜索词报告分析器 v3.0（场景化框架）

核心变更（相对 v2 的 8 分类框架）：
- 场景路由：自家 ASIN 在/不在该词点击 TOP3，走完全不同的业务判断
  - 场景 A（在 TOP3）：看自家行的成交系数 → A1 收割 / A2 漏水 / A4 份额预警 / A5 平衡
  - 场景 B（不在 TOP3）：点击集中度 × 头部满足度四象限 → B1 机会 / B2 常规竞争 /
    B3 头部满足 / B4 伏击 + B0 数据不足
- 缺失数据不再当 0：转化份额全空/全 0 单列"转化分散或脱敏"，不参与象限判定
- 阈值全部参数化，默认值为多源实战经验值（详见 关键词分类逻辑说明.md）
- 数据粒度自动识别（周报/月报），所有统计按"期"计，不再假设月报
"""

import argparse
import json
import re
import os
import glob
import warnings
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings('ignore')

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style('whitegrid')

# ---------------------------------------------------------------------------
# 常量与默认词表
# ---------------------------------------------------------------------------

STOP_WORDS = {
    'for', 'with', 'and', 'the', 'of', 'in', 'to', 'a', 'an',
    'on', 'at', 'by', 'from', 'up', 'about', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'between',
    'under', 'again', 'further', 'then', 'once', '&', '-', '/',
}

DEFAULT_TERM_LEXICON = {
    'audience_words': {
        'women', 'men', 'man', 'woman', 'kids', 'kid', 'children', 'child',
        'boys', 'boy', 'girls', 'girl', 'teen', 'adult', 'college', 'business', 'professional',
    },
    'scene_words': {
        'travel', 'work', 'school', 'gaming', 'outdoor', 'gym', 'office', 'home',
        'car', 'camping', 'hiking', 'running', 'sports',
    },
    'attribute_words': {
        'waterproof', 'leather', 'large', 'small', 'slim', 'lightweight',
        'durable', 'portable', 'anti', 'theft', 'usb', 'charging',
    },
}

DEFAULT_WORD_LEXICON = {
    'audience_words': {
        'women', 'men', 'man', 'woman', 'kids', 'kid', 'children', 'child',
        'boys', 'boy', 'girls', 'girl', 'college', 'student', 'business',
        'professional', 'teen', 'adult', 'ladies', 'lady', 'mens', 'womens',
    },
    'scene_words': {
        'travel', 'work', 'school', 'gaming', 'outdoor', 'hiking', 'camping',
        'office', 'gym', 'sports', 'running', 'cycling', 'commute', 'daily',
        'casual', 'weekend', 'vacation',
    },
    'attribute_words': {
        'large', 'small', 'big', 'mini', 'slim', 'lightweight', 'heavy',
        'waterproof', 'leather', 'canvas', 'nylon', 'durable', 'portable',
        'foldable', 'expandable', 'anti', 'theft', 'resistant', 'proof',
        'inch', '15', '16', '17', '18', 'capacity', 'compartment',
    },
}

# 阈值默认值均为多源实战经验值（业内共识），按类目校准，全部可由 CLI 覆盖
DEFAULT_THRESHOLDS = {
    'click_conc_scattered': 30.0,     # TOP3 点击集中度 < 此值 = 未整合市场
    'click_conc_concentrated': 50.0,  # ≥ 此值 = 集中市场（B3/B4）
    'monopoly_redline': 70.0,         # 点击或转化集中度 ≥ 此值 = 垄断红线
    'coefficient_threshold': 1.0,     # 成交系数 / 头部满足度分界
    'own_gap_points': 4.0,            # 自家 点击份额-转化份额 > 此差值 = 漏水
    'sfr_tiers': [10000, 20000, 50000, 100000],  # SFR 五级分层边界
    'bluesea_sfr': 200000,            # 蓝海信号：SFR 深于此
    'bluesea_share': 60.0,            # 且 TOP3 份额集中度高于此
}

SCENARIO_B_ADVICE = {
    'B1机会词': '优先级最高：确认产品能接住该词意图后，优先投放并进 Listing；先核对 TOP3 属性一致性',
    'B2常规竞争词': '可进：常规差异化 + 正常出价测试',
    'B3头部满足词': '避其锋芒：不正面竞价，找相邻长尾/差异化词切入',
    'B4伏击词': '伏击打法：竞品定向 + 压价，用转化力偷单，不打点击战',
    'B0数据不足': '不判定：转化数据缺失或分散/脱敏，转 SQP 或广告数据验证后再决策',
}

SCENARIO_A_ADVICE = {
    'A1收割词': '防守 + 放量：加预算、防御性投放、盯竞品进入',
    'A2漏水词': '先修详情页再抬价：排查价格/评价/主图/A+，用 SQP 定位漏斗卡点',
    'A4份额预警': '已掉出该词点击 TOP3：排查排名/价格/断货/新竞品，触发竞品深挖',
    'A5平衡词': '维持现状，周度跟踪份额变化',
}


def load_category_lexicon(path):
    """读取可选品类词表 JSON；缺少的组继续使用内置初筛词表。"""
    if not path:
        return {}
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError('--category-lexicon 根节点必须是 JSON object')

    allowed = {'audience_words', 'scene_words', 'attribute_words'}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"--category-lexicon 包含未知字段: {', '.join(unknown)}")

    normalized = {}
    for key, values in payload.items():
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise ValueError(f'--category-lexicon 的 {key} 必须是字符串数组')
        normalized[key] = {item.strip().lower() for item in values if item.strip()}
    return normalized


def _fmt(value, digits=2, empty=''):
    """NaN 安全的数值格式化：缺失显示为空而不是 0。"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return empty
    return f'{value:.{digits}f}'


def _fmt_int(value, empty=''):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return empty
    return str(int(value))


class AmazonSearchAnalyzer:
    """Brand Analytics 热门搜索词分析器 v3.0"""

    CLICK_COLS = [f'点击量最高的商品 #{i}：点击份额' for i in range(1, 4)]
    CONV_COLS = [f'点击量最高的商品 #{i}：转化份额' for i in range(1, 4)]
    ASIN_COLS = [f'点击量最高的商品 #{i}：ASIN' for i in range(1, 4)]

    def __init__(self, data_dir, category_lexicon=None, own_asins=None, thresholds=None):
        self.data_dir = data_dir
        self.df = None
        self.reports_dir = os.path.join(data_dir, 'analysis_reports')
        self.term_lexicon = {k: set(v) for k, v in DEFAULT_TERM_LEXICON.items()}
        self.word_lexicon = {k: set(v) for k, v in DEFAULT_WORD_LEXICON.items()}
        custom = load_category_lexicon(category_lexicon)
        for key, values in custom.items():
            self.term_lexicon[key] = set(values)
            self.word_lexicon[key] = set(values)
        self.own_asins = {a.strip().upper() for a in (own_asins or []) if a.strip()}
        self.th = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            self.th.update(thresholds)
        self.granularity = '未知'
        self.term_df = None       # 03 的核心产物，供 04-07 复用
        self.product_df = None    # (词, 期, 位次, ASIN, 份额) 明细，供 05/06 复用
        os.makedirs(self.reports_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 数据加载与清洗
    # ------------------------------------------------------------------

    def load_all_data(self):
        csv_files = sorted(glob.glob(os.path.join(self.data_dir, '*.csv')))
        if not csv_files:
            print(f'❌ 未找到CSV文件: {self.data_dir}')
            return False

        print(f'\n📂 找到 {len(csv_files)} 个CSV文件')
        frames = []
        for file in csv_files:
            print(f'   Loading: {os.path.basename(file)}')
            try:
                frames.append(self._read_one(file))
            except Exception as exc:
                print(f'   ⚠️  Error loading {file}: {exc}')
        if not frames:
            return False

        df = pd.concat(frames, ignore_index=True)
        # 同一 (搜索词, 报告日期) 跨文件重复时只保留一份，避免重复计数
        before = len(df)
        df = df.drop_duplicates(subset=['搜索词', '报告日期'], keep='first')
        if len(df) < before:
            print(f'   ℹ️  去除跨文件重复行 {before - len(df)} 条')
        self.df = df
        print(f'\n✅ 总记录数: {len(self.df)}')
        return True

    @staticmethod
    def _read_one(path):
        """自动识别首行是标题行还是元信息行。"""
        probe = pd.read_csv(path, nrows=1, header=None, encoding='utf-8-sig')
        first_line = ','.join(str(x) for x in probe.iloc[0].tolist())
        skip = 0 if ('搜索词' in first_line and '搜索频率排名' in first_line) else 1
        return pd.read_csv(path, skiprows=skip, encoding='utf-8-sig')

    def clean_data(self):
        print('\n🧹 数据清洗中...')
        df = self.df
        required = ['搜索词', '搜索频率排名', '报告日期']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f'缺少必需字段: {missing}；请确认是 Brand Analytics 热门搜索词报告')

        df['搜索频率排名'] = pd.to_numeric(df['搜索频率排名'], errors='coerce')
        df['报告日期'] = pd.to_datetime(df['报告日期'], errors='coerce')
        df = df.dropna(subset=['搜索词', '报告日期'])
        df['期'] = df['报告日期'].dt.strftime('%Y-%m-%d')

        # 份额字段：容忍 "12.34%" 字符串；保留 NaN（缺失≠0，数据诚信红线）
        for col in self.CLICK_COLS + self.CONV_COLS:
            if col not in df.columns:
                df[col] = np.nan
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.rstrip('%').replace({'nan': None, '': None})
            df[col] = pd.to_numeric(df[col], errors='coerce')
        for col in self.ASIN_COLS:
            if col not in df.columns:
                df[col] = np.nan

        self.df = df
        self.granularity = self._detect_granularity(df['报告日期'])
        print(f'   数据维度: {df.shape}')
        print(f'   数据粒度: {self.granularity} | 期数: {df["期"].nunique()}')
        print(f'   时间范围: {df["报告日期"].min().date()} 至 {df["报告日期"].max().date()}')
        print(f'   独特搜索词: {df["搜索词"].nunique()}')
        if self.own_asins:
            print(f'   自家 ASIN: {len(self.own_asins)} 个（场景 A/B 路由已启用）')
        else:
            print('   ⚠️ 未提供自家 ASIN，全部按场景 B（市场进入视角）分析')

    @staticmethod
    def _detect_granularity(dates):
        uniq = sorted(dates.dropna().unique())
        if len(uniq) < 2:
            return '单期'
        diffs = np.diff(uniq).astype('timedelta64[D]').astype(int)
        med = float(np.median(diffs))
        if med <= 10:
            return '周报'
        if med <= 45:
            return '月报'
        return '季报'

    # ------------------------------------------------------------------
    # 通用报告头
    # ------------------------------------------------------------------

    def _data_context(self):
        dates = self.df['报告日期'].dropna()
        if dates.empty:
            return '暂无', 0
        rng = f"{dates.min().strftime('%Y-%m-%d')} 至 {dates.max().strftime('%Y-%m-%d')}"
        return rng, int(self.df['期'].nunique())

    def _write_report_header(self, f):
        rng, n = self._data_context()
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f'**数据时间范围**: {rng}（{self.granularity}，共 {n} 期）\n')
        own_note = f'{len(self.own_asins)} 个' if self.own_asins else '未提供（全部按场景 B 市场视角分析）'
        f.write(f'**自家 ASIN**: {own_note}\n')
        f.write('**口径提醒**: 搜索频率排名是相对排名不是搜索量；点击份额与转化份额是独立指标；'
                'TOP3 是"点击最多"的 3 个 ASIN（含广告位点击），不是转化最高的 3 个\n\n')

    # ------------------------------------------------------------------
    # 03 核心：场景化搜索词分析
    # ------------------------------------------------------------------

    def _sfr_tier(self, rank):
        if rank is None or (isinstance(rank, float) and np.isnan(rank)):
            return '未知'
        t = self.th['sfr_tiers']
        if rank <= t[0]:
            return 'T1核心大词'
        if rank <= t[1]:
            return 'T2次核心大词'
        if rank <= t[2]:
            return 'T3中量词'
        if rank <= t[3]:
            return 'T4中长尾'
        return 'T5长尾'

    def _brand_patterns(self):
        """品牌词匹配：词边界正则，跳过过短品牌名避免误报。"""
        patterns = []
        for i in range(1, 4):
            col = f'点击量最高的品牌 #{i}'
            if col not in self.df.columns:
                continue
            series = self.df[col].dropna().astype(str).str.strip().str.lower()
            for brand in series[series != ''].unique():
                if len(brand) >= 3:
                    patterns.append(re.compile(r'(?<!\w)' + re.escape(brand) + r'(?!\w)'))
        return patterns

    def _keyword_tags(self, term_lower, words_in_term, brand_patterns):
        tags = []
        if words_in_term & self.term_lexicon['audience_words']:
            tags.append('人群词')
        if words_in_term & self.term_lexicon['scene_words']:
            tags.append('场景词')
        if words_in_term & self.term_lexicon['attribute_words']:
            tags.append('属性词')
        if any(p.search(term_lower) for p in brand_patterns):
            tags.append('品牌词')
        return '/'.join(tags) if tags else '通用词'

    def analyze_search_scenarios(self):
        print('\n📊 3/7 搜索词场景分析（核心）...')
        brand_patterns = self._brand_patterns()
        th = self.th
        rows = []

        for term, g in self.df.groupby('搜索词', sort=False):
            g = g.sort_values('报告日期')
            ranks = g['搜索频率排名'].dropna()
            n_periods = int(g['期'].nunique())

            if ranks.empty:
                sfr_avg = sfr_latest = best = worst = std = np.nan
                best_p = worst_p = ''
            else:
                sfr_avg = float(ranks.mean())
                sfr_latest = float(g.dropna(subset=['搜索频率排名']).iloc[-1]['搜索频率排名'])
                best = float(ranks.min())
                worst = float(ranks.max())
                std = float(ranks.std()) if len(ranks) > 1 else 0.0
                best_p = g.loc[g['搜索频率排名'].idxmin(), '期']
                worst_p = g.loc[g['搜索频率排名'].idxmax(), '期']

            # --- TOP3 合计份额（按期求和后跨期取均值；min_count=1 保 NaN 语义）---
            click_by_period = g[self.CLICK_COLS].sum(axis=1, min_count=1)
            conv_by_period = g[self.CONV_COLS].sum(axis=1, min_count=1)
            click_conc = float(click_by_period.mean()) if click_by_period.notna().any() else np.nan
            conv_conc = float(conv_by_period.mean()) if conv_by_period.notna().any() else np.nan
            conv_present = g[self.CONV_COLS].notna().any().any()

            if np.isnan(click_conc):
                data_state = '点击数据缺失'
            elif not conv_present:
                data_state = '转化数据缺失'
            elif conv_conc == 0:
                data_state = '转化分散或脱敏'
            else:
                data_state = '正常'

            ratio = (conv_conc / click_conc) if (data_state == '正常' and click_conc > 0) else np.nan

            # --- 场景路由 ---
            latest = g.iloc[-1]
            latest_top3 = {str(latest[c]).strip().upper() for c in self.ASIN_COLS if pd.notna(latest[c])}
            own_ever = False
            own_click_series = []
            if self.own_asins:
                for _, row in g.iterrows():
                    period_own_click = np.nan
                    hit = False
                    for i in range(3):
                        asin = row[self.ASIN_COLS[i]]
                        if pd.notna(asin) and str(asin).strip().upper() in self.own_asins:
                            hit = True
                            c = row[self.CLICK_COLS[i]]
                            if pd.notna(c):
                                period_own_click = (0 if np.isnan(period_own_click) else period_own_click) + float(c)
                    own_ever = own_ever or hit
                    own_click_series.append(period_own_click if hit else np.nan)

            scenario = 'A' if own_ever else 'B'
            own_click_latest = own_conv_latest = own_coeff = np.nan
            state = ''
            flags = []
            intercept_targets = []

            # 截流目标：最新一期 TOP3 中转化数据齐全且成交系数 < 1 的非自家 ASIN
            for i in range(3):
                asin = latest[self.ASIN_COLS[i]]
                c, v = latest[self.CLICK_COLS[i]], latest[self.CONV_COLS[i]]
                if pd.isna(asin) or pd.isna(c) or pd.isna(v) or c <= 0:
                    continue
                asin_u = str(asin).strip().upper()
                if asin_u in self.own_asins:
                    continue
                if v / c < th['coefficient_threshold'] and (c - v) > 0:
                    intercept_targets.append(asin_u)

            if scenario == 'A':
                own_in_latest = bool(latest_top3 & self.own_asins)
                if own_in_latest:
                    oc = ov = np.nan
                    for i in range(3):
                        asin = latest[self.ASIN_COLS[i]]
                        if pd.notna(asin) and str(asin).strip().upper() in self.own_asins:
                            c, v = latest[self.CLICK_COLS[i]], latest[self.CONV_COLS[i]]
                            if pd.notna(c):
                                oc = (0 if np.isnan(oc) else oc) + float(c)
                            if pd.notna(v):
                                ov = (0 if np.isnan(ov) else ov) + float(v)
                    own_click_latest, own_conv_latest = oc, ov
                    if pd.notna(oc) and pd.notna(ov) and oc > 0:
                        own_coeff = ov / oc

                if not own_in_latest:
                    state = 'A4份额预警'
                    flags.append('曾在TOP3、最新一期掉出')
                elif np.isnan(own_conv_latest):
                    state = 'A5平衡词'
                    flags.append('自家转化数据缺失')
                elif (own_click_latest - own_conv_latest) > th['own_gap_points']:
                    state = 'A2漏水词'
                elif own_coeff >= th['coefficient_threshold']:
                    state = 'A1收割词'
                else:
                    state = 'A5平衡词'

                # 份额下滑预警（需 ≥3 期自家点击数据且严格递减）
                oc_valid = [x for x in own_click_series if not (isinstance(x, float) and np.isnan(x))]
                if len(oc_valid) >= 3 and all(a > b for a, b in zip(oc_valid[-3:], oc_valid[-2:])):
                    flags.append('自家点击份额连续下滑')
            else:
                if data_state != '正常':
                    state = 'B0数据不足'
                elif click_conc >= th['click_conc_concentrated']:
                    state = 'B3头部满足词' if ratio >= th['coefficient_threshold'] else 'B4伏击词'
                else:
                    state = 'B2常规竞争词' if ratio >= th['coefficient_threshold'] else 'B1机会词'

            redline = ''
            if (not np.isnan(click_conc) and click_conc >= th['monopoly_redline']) or \
               (not np.isnan(conv_conc) and conv_conc >= th['monopoly_redline']):
                redline = '是'
            bluesea = ''
            if not np.isnan(sfr_avg) and sfr_avg >= th['bluesea_sfr']:
                top_share = np.nanmax([click_conc, conv_conc])
                if not np.isnan(top_share) and top_share >= th['bluesea_share']:
                    bluesea = '是'

            term_lower = str(term).lower()
            words_in_term = set(re.findall(r'\b\w+\b', term_lower))
            advice = SCENARIO_A_ADVICE.get(state) or SCENARIO_B_ADVICE.get(state, '')

            rows.append({
                '搜索词': term,
                '平均搜索频率排名': round(sfr_avg) if not np.isnan(sfr_avg) else np.nan,
                '最新排名': round(sfr_latest) if not np.isnan(sfr_latest) else np.nan,
                'SFR层级': self._sfr_tier(sfr_avg),
                '出现期数': n_periods,
                '最佳排名': round(best) if not np.isnan(best) else np.nan,
                '最佳排名期': best_p,
                '最差排名': round(worst) if not np.isnan(worst) else np.nan,
                '最差排名期': worst_p,
                '排名标准差': round(std, 2) if not np.isnan(std) else np.nan,
                '关键词标签': self._keyword_tags(term_lower, words_in_term, brand_patterns),
                '点击集中度TOP3(%)': round(click_conc, 2) if not np.isnan(click_conc) else np.nan,
                '转化集中度TOP3(%)': round(conv_conc, 2) if not np.isnan(conv_conc) else np.nan,
                '头部满足度': round(ratio, 2) if not np.isnan(ratio) else np.nan,
                '数据状态': data_state,
                '场景': scenario,
                '状态': state,
                '垄断红线': redline,
                '蓝海信号': bluesea,
                '自家点击份额(%)': round(own_click_latest, 2) if not np.isnan(own_click_latest) else np.nan,
                '自家转化份额(%)': round(own_conv_latest, 2) if not np.isnan(own_conv_latest) else np.nan,
                '自家成交系数': round(own_coeff, 2) if not np.isnan(own_coeff) else np.nan,
                '截流目标ASIN': '/'.join(intercept_targets),
                '备注': '；'.join(flags),
                '动作建议': advice,
            })

        term_df = pd.DataFrame(rows).sort_values('平均搜索频率排名')
        self.term_df = term_df
        term_df.to_csv(os.path.join(self.reports_dir, '03_搜索词热度分析.csv'),
                       index=False, encoding='utf-8-sig')
        self._generate_scenario_report(term_df)
        print(f'   ✓ 分析 {len(term_df)} 个搜索词 | 场景A {int((term_df["场景"] == "A").sum())} 个'
              f' | 场景B {int((term_df["场景"] == "B").sum())} 个')
        print('   ✓ 输出文件: 03_搜索词热度分析.csv + .md')
        return term_df

    def _generate_scenario_report(self, tdf):
        md_path = os.path.join(self.reports_dir, '03_搜索词热度分析.md')
        th = self.th
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 搜索词场景分析报告（热度 + 市场结构）\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            f.write('> **标签口径**：关键词标签为词面词典命中，仅作初筛；买家意图判断由 AI 注解层增量补充。\n\n')

            # 框架说明
            f.write('## 🧭 场景框架说明\n\n')
            f.write('**场景路由**：自家 ASIN 在该词点击 TOP3 → 场景 A（存量经营）；不在 → 场景 B（市场进入）。\n\n')
            f.write('**场景 A 状态**（依据自家行的成交系数 = 自家转化份额 ÷ 自家点击份额）：\n\n')
            f.write('| 状态 | 判定 | 动作 |\n|---|---|---|\n')
            f.write(f"| A1收割词 | 成交系数 ≥ {th['coefficient_threshold']} | {SCENARIO_A_ADVICE['A1收割词']} |\n")
            f.write(f"| A2漏水词 | 点击份额 − 转化份额 > {th['own_gap_points']}pt | {SCENARIO_A_ADVICE['A2漏水词']} |\n")
            f.write(f"| A4份额预警 | 曾在 TOP3、最新一期掉出 | {SCENARIO_A_ADVICE['A4份额预警']} |\n")
            f.write(f"| A5平衡词 | 介于两者之间 | {SCENARIO_A_ADVICE['A5平衡词']} |\n\n")
            f.write('**场景 B 象限**（点击集中度 = TOP3 点击份额之和；头部满足度 = TOP3 转化份额之和 ÷ 点击份额之和）：\n\n')
            f.write('| 象限 | 判定 | 结构解读 | 动作 |\n|---|---|---|---|\n')
            f.write(f"| B1机会词 | 集中度 < {th['click_conc_concentrated']}% 且 满足度 < {th['coefficient_threshold']} "
                    f"| 点击分散且头部接不住需求，转化流向 TOP3 之外 | {SCENARIO_B_ADVICE['B1机会词']} |\n")
            f.write(f"| B2常规竞争词 | 集中度 < {th['click_conc_concentrated']}% 且 满足度 ≥ {th['coefficient_threshold']} "
                    f"| 蛋糕未整合、头部转化健康 | {SCENARIO_B_ADVICE['B2常规竞争词']} |\n")
            f.write(f"| B3头部满足词 | 集中度 ≥ {th['click_conc_concentrated']}% 且 满足度 ≥ {th['coefficient_threshold']} "
                    f"| 头部垄断且高效满足市场 | {SCENARIO_B_ADVICE['B3头部满足词']} |\n")
            f.write(f"| B4伏击词 | 集中度 ≥ {th['click_conc_concentrated']}% 且 满足度 < {th['coefficient_threshold']} "
                    f"| 头部霸点击但买家买了别家 | {SCENARIO_B_ADVICE['B4伏击词']} |\n")
            f.write(f"| B0数据不足 | 转化数据缺失/分散/脱敏 | 无法判定头部满足度 | {SCENARIO_B_ADVICE['B0数据不足']} |\n\n")
            f.write(f"**附加信号**：垄断红线 = 点击或转化集中度 ≥ {th['monopoly_redline']}%；"
                    f"蓝海信号 = SFR ≥ {int(th['bluesea_sfr'])} 且 TOP3 份额 ≥ {th['bluesea_share']}%（未开发利基）。\n\n")

            # 摘要
            f.write('## 📊 数据事实：执行摘要\n\n')
            f.write(f'- **总搜索词数**: {len(tdf)}\n')
            order = ['A1收割词', 'A2漏水词', 'A4份额预警', 'A5平衡词',
                     'B1机会词', 'B2常规竞争词', 'B3头部满足词', 'B4伏击词', 'B0数据不足']
            counts = tdf['状态'].value_counts()
            for s in order:
                if counts.get(s, 0):
                    f.write(f'- **{s}**: {counts[s]} 个\n')
            n_red = int((tdf['垄断红线'] == '是').sum())
            n_blue = int((tdf['蓝海信号'] == '是').sum())
            if n_red:
                f.write(f'- **触发垄断红线**: {n_red} 个\n')
            if n_blue:
                f.write(f'- **蓝海信号**: {n_blue} 个\n')
            f.write('\n')

            # 各状态明细
            cols_a = ['搜索词', '平均搜索频率排名', 'SFR层级', '自家点击份额(%)', '自家转化份额(%)',
                      '自家成交系数', '截流目标ASIN', '备注']
            cols_b = ['搜索词', '平均搜索频率排名', 'SFR层级', '点击集中度TOP3(%)', '转化集中度TOP3(%)',
                      '头部满足度', '垄断红线', '蓝海信号', '关键词标签']
            for s in order:
                sub = tdf[tdf['状态'] == s]
                if sub.empty:
                    continue
                f.write(f'## {s}（{len(sub)} 个）\n\n')
                f.write(f'> {SCENARIO_A_ADVICE.get(s) or SCENARIO_B_ADVICE.get(s, "")}\n\n')
                cols = cols_a if s.startswith('A') else cols_b
                f.write('| ' + ' | '.join(cols) + ' |\n')
                f.write('|' + '---|' * len(cols) + '\n')
                for _, r in sub.head(20).iterrows():
                    vals = []
                    for c in cols:
                        v = r[c]
                        if isinstance(v, float):
                            vals.append(_fmt(v))
                        else:
                            vals.append('' if pd.isna(v) else str(v))
                    f.write('| ' + ' | '.join(vals) + ' |\n')
                if len(sub) > 20:
                    f.write(f'\n*（仅列 TOP20，完整 {len(sub)} 条见 CSV）*\n')
                f.write('\n')

            # 数据说明
            f.write('---\n\n**数据说明**:\n')
            f.write('- 排名是全平台相对排名，不是搜索量；跨类目不可比\n')
            f.write('- TOP3 是"点击最多"的 3 个 ASIN（含广告位点击），转化最高的 ASIN 可能不在其中\n')
            f.write('- 点击份额与转化份额是独立指标：TOP3 转化份额为 0/缺失是常见真实现象（转化分散到长尾或被脱敏），'
                    '已单列 B0 不参与象限判定\n')
            f.write('- 所有阈值为多源实战经验默认值，按类目校准（见 关键词分类逻辑说明.md）\n')

    # ------------------------------------------------------------------
    # 01 品牌竞争分析
    # ------------------------------------------------------------------

    def analyze_brands(self):
        print('\n📊 1/7 品牌竞争分析...')
        from collections import Counter
        brand_counts = Counter()
        brand_positions = {1: Counter(), 2: Counter(), 3: Counter()}
        for i in range(1, 4):
            col = f'点击量最高的品牌 #{i}'
            if col not in self.df.columns:
                continue
            brands = self.df[col].dropna().astype(str).str.strip()
            brands = brands[brands != '']
            brand_counts.update(brands)
            brand_positions[i].update(brands)

        data = []
        total = sum(brand_counts.values())
        for rank, (brand, cnt) in enumerate(brand_counts.most_common(30), start=1):
            data.append({
                '排名': rank,
                '品牌': brand,
                '#1位次数': brand_positions[1][brand],
                '#2位次数': brand_positions[2][brand],
                '#3位次数': brand_positions[3][brand],
                '总上榜次数': cnt,
                '上榜次数占比': f'{cnt / total * 100:.2f}%',
            })
        brand_df = pd.DataFrame(data)
        brand_df.to_csv(os.path.join(self.reports_dir, '01_品牌竞争分析.csv'),
                        index=False, encoding='utf-8-sig')

        md_path = os.path.join(self.reports_dir, '01_品牌竞争分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 品牌竞争分析报告\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            if brand_df.empty:
                f.write('## 📊 数据事实\n\n')
                f.write('- 本次输入未提供 Top Brand 数据（领星 ABA 源不含品牌字段），跳过品牌竞争排名。\n')
                f.write('- 不影响搜索词场景、词频、竞争格局与成交系数分析。\n')
            else:
                top3 = brand_df.head(3)
                f.write('## 📊 数据事实：执行摘要\n\n')
                f.write(f"- **上榜最多品牌**: {top3.iloc[0]['品牌']}（{top3.iloc[0]['总上榜次数']} 次）\n")
                f.write(f"- **TOP 3 品牌**: {', '.join(top3['品牌'])}\n")
                f.write(f'- **总品牌数**: {len(brand_df)}\n\n')
                f.write('> ⚠️ 口径：这里的占比是"在各搜索词点击 TOP3 位置出现的频次占比"，'
                        '反映品牌对热搜词的覆盖广度，**不是市场销售份额**。\n\n')
                f.write('## 🏆 TOP 10 品牌上榜排名\n\n')
                f.write('| 排名 | 品牌 | #1位 | #2位 | #3位 | 总上榜次数 | 上榜次数占比 |\n')
                f.write('|------|------|------|------|------|------|------|\n')
                for _, r in brand_df.head(10).iterrows():
                    f.write(f"| {r['排名']} | {r['品牌']} | {r['#1位次数']} | {r['#2位次数']} | "
                            f"{r['#3位次数']} | {r['总上榜次数']} | {r['上榜次数占比']} |\n")
                f.write('\n## 💡 分析推断：实操建议\n\n')
                brands_str = ', '.join(top3['品牌'])
                f.write(f'- 高频上榜品牌（{brands_str}）是该词群的流量守门人：'
                        '新品避免正面竞价其品牌词，优先差异化定位\n')
                f.write('- 关注腰部品牌（6-15 名）的打法：它们在头部夹缝中活下来的方式可复用\n')
                f.write('- 品牌词防御：若自家品牌上榜，对自家品牌词做防御性投放\n')
        print(f'   ✓ 识别 {len(brand_df)} 个品牌 | 输出: 01_品牌竞争分析.csv + .md')
        return brand_df

    # ------------------------------------------------------------------
    # 02 类别趋势分析
    # ------------------------------------------------------------------

    def analyze_categories(self):
        print('\n📊 2/7 类别趋势分析...')
        from collections import Counter
        cat_counts = Counter()
        cat_positions = {1: Counter(), 2: Counter(), 3: Counter()}
        for i in range(1, 4):
            col = f'点击量最高的类别 #{i}'
            if col not in self.df.columns:
                continue
            cats = self.df[col].dropna().astype(str).str.strip()
            cats = cats[cats != '']
            cat_counts.update(cats)
            cat_positions[i].update(cats)

        data = []
        total = sum(cat_counts.values()) or 1
        for rank, (cat, cnt) in enumerate(cat_counts.most_common(20), start=1):
            data.append({
                '排名': rank, '类别': cat,
                '#1位次数': cat_positions[1][cat],
                '#2位次数': cat_positions[2][cat],
                '#3位次数': cat_positions[3][cat],
                '总出现次数': cnt,
                '占比': f'{cnt / total * 100:.2f}%',
            })
        cat_df = pd.DataFrame(data)
        cat_df.to_csv(os.path.join(self.reports_dir, '02_类别趋势分析.csv'),
                      index=False, encoding='utf-8-sig')

        md_path = os.path.join(self.reports_dir, '02_类别趋势分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 类别趋势分析报告\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            if cat_df.empty:
                f.write('## 📊 数据事实\n\n- 本次输入未提供类别数据，跳过。\n')
            else:
                top = cat_df.iloc[0]
                f.write('## 📊 数据事实：执行摘要\n\n')
                f.write(f"- **主导类别**: {top['类别']}（占比 {top['占比']}）\n")
                f.write(f"- **TOP 3 类别**: {', '.join(cat_df.head(3)['类别'])}\n")
                f.write(f'- **总类别数**: {len(cat_df)}\n\n')
                f.write('## 🏆 TOP 10 类别\n\n')
                f.write('| 排名 | 类别 | #1位 | #2位 | #3位 | 总次数 | 占比 |\n')
                f.write('|------|------|------|------|------|--------|------|\n')
                for _, r in cat_df.head(10).iterrows():
                    f.write(f"| {r['排名']} | {r['类别']} | {r['#1位次数']} | {r['#2位次数']} | "
                            f"{r['#3位次数']} | {r['总出现次数']} | {r['占比']} |\n")
                f.write('\n## 💡 分析推断：实操建议\n\n')
                f.write(f"- 主分类优先选择 **{top['类别']}**；若与现有节点不符，评估类目节点迁移\n")
                f.write('- 次要类别（4-8 名）提示跨类目机会：Listing 文案与 A+ 可覆盖对应场景\n')
        print(f'   ✓ 识别 {len(cat_df)} 个类别 | 输出: 02_类别趋势分析.csv + .md')
        return cat_df

    # ------------------------------------------------------------------
    # 04 词频统计（按去重搜索词计数）
    # ------------------------------------------------------------------

    def analyze_word_frequency(self):
        print('\n📊 4/7 词频统计分析...')
        from collections import Counter
        if self.term_df is None:
            raise RuntimeError('需先运行 analyze_search_scenarios')

        term_rank = dict(zip(self.term_df['搜索词'], self.term_df['平均搜索频率排名']))
        word_counter, word_terms = Counter(), {}
        bigram_counter, bigram_terms = Counter(), {}

        for term in term_rank:
            term_l = str(term).lower()
            tokens = re.findall(r'\b\w+\b', term_l)
            content = [w for w in tokens if w not in STOP_WORDS and len(w) > 1]
            for w in set(content):
                word_counter[w] += 1
                word_terms.setdefault(w, []).append(term)
            # 双词短语：只取原始序列中真正相邻、且双方都是内容词的组合，不跨停用词拼接
            seen_bigrams = set()
            for a, b in zip(tokens, tokens[1:]):
                if a in STOP_WORDS or b in STOP_WORDS or len(a) <= 1 or len(b) <= 1:
                    continue
                bg = f'{a} {b}'
                if bg in seen_bigrams:
                    continue
                seen_bigrams.add(bg)
                bigram_counter[bg] += 1
                bigram_terms.setdefault(bg, []).append(term)

        def build_table(counter, mapping, key_name):
            data = []
            for rank, (key, cnt) in enumerate(counter.most_common(100), start=1):
                terms = mapping[key]
                ranked = [(t, term_rank.get(t)) for t in terms]
                ranked = [(t, r) for t, r in ranked if r is not None and not pd.isna(r)]
                best = min(ranked, key=lambda x: x[1]) if ranked else (terms[0], np.nan)
                avg = np.mean([r for _, r in ranked]) if ranked else np.nan
                row = {
                    '排名': rank, key_name: key,
                    '覆盖搜索词数': cnt,
                    '最佳搜索词示例': best[0],
                    '该搜索词排名': _fmt_int(best[1]),
                    '覆盖词平均排名': _fmt_int(avg),
                }
                if key_name == '单词':
                    row['词汇类型'] = self._classify_word(key)
                data.append(row)
            return pd.DataFrame(data)

        word_df = build_table(word_counter, word_terms, '单词')
        if not word_df.empty:
            word_df = word_df[['排名', '单词', '覆盖搜索词数', '词汇类型',
                               '最佳搜索词示例', '该搜索词排名', '覆盖词平均排名']]
        bigram_df = build_table(bigram_counter, bigram_terms, '双词短语')

        xlsx = os.path.join(self.reports_dir, '04_词频统计分析.xlsx')
        with pd.ExcelWriter(xlsx, engine='openpyxl') as writer:
            word_df.to_excel(writer, sheet_name='单词词频统计', index=False)
            bigram_df.to_excel(writer, sheet_name='双词短语统计', index=False)

        md_path = os.path.join(self.reports_dir, '04_词频统计分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 搜索词词频统计分析报告\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            f.write('> **口径**：按**去重后的搜索词**计数（一个词在多期出现只计一次）；'
                    '双词短语只统计原始搜索词中真正相邻的内容词组合，不跨停用词拼接。\n\n')
            f.write('## 📊 数据事实：执行摘要\n\n')
            if not word_df.empty:
                f.write(f"- **最高频词**: {word_df.iloc[0]['单词']}（覆盖 {word_df.iloc[0]['覆盖搜索词数']} 个搜索词）\n")
            if not bigram_df.empty:
                f.write(f"- **最高频短语**: {bigram_df.iloc[0]['双词短语']}"
                        f"（覆盖 {bigram_df.iloc[0]['覆盖搜索词数']} 个搜索词）\n")
            f.write('\n## 🔤 TOP 30 高频词汇\n\n')
            f.write('| 排名 | 单词 | 覆盖搜索词数 | 类型 | 最佳搜索词示例 | 该词排名 |\n')
            f.write('|------|------|------|------|------|------|\n')
            for _, r in word_df.head(30).iterrows():
                f.write(f"| {r['排名']} | **{r['单词']}** | {r['覆盖搜索词数']} | {r['词汇类型']} | "
                        f"{str(r['最佳搜索词示例'])[:40]} | {r['该搜索词排名']} |\n")
            f.write('\n## 🔗 TOP 30 高频双词短语\n\n')
            f.write('| 排名 | 双词短语 | 覆盖搜索词数 | 最佳搜索词示例 | 该词排名 |\n')
            f.write('|------|------|------|------|------|\n')
            for _, r in bigram_df.head(30).iterrows():
                f.write(f"| {r['排名']} | **{r['双词短语']}** | {r['覆盖搜索词数']} | "
                        f"{str(r['最佳搜索词示例'])[:40]} | {r['该搜索词排名']} |\n")
            f.write('\n## 🏷️ 词汇分类汇总\n\n')
            if not word_df.empty:
                for wt in ['人群词', '场景词', '属性词', '品牌词', '核心词']:
                    sub = word_df[word_df['词汇类型'] == wt]
                    if not sub.empty:
                        f.write(f'### {wt} TOP 10\n\n')
                        for _, r in sub.head(10).iterrows():
                            f.write(f"- **{r['单词']}**（覆盖 {r['覆盖搜索词数']} 个搜索词）\n")
                        f.write('\n')
            f.write('## 💡 分析推断：实操建议\n\n')
            f.write('- **标题结构参考**：品牌词 + 核心词 + 高频属性词 + 人群词 + 场景词；'
                    '高频词原词呈现在标题可提升搜索结果页的相关性感知\n')
            f.write('- **广告选词**：高频双词短语可直接作精准/词组匹配候选（均为用户真实相邻搜索组合）\n')
            f.write('- **五点/A+**：每个 bullet 围绕一个场景词或人群词展开，对应一组买家意图\n\n')
            f.write('---\n\n**数据说明**: 基于去重搜索词的词面拆解统计，已过滤常见停用词\n')

        print(f'   ✓ 高频词 {len(word_df)} 个 | 高频短语 {len(bigram_df)} 个 | 输出: 04_词频统计分析.xlsx + .md')
        return word_df, bigram_df

    def _classify_word(self, word):
        if word in self.word_lexicon['audience_words']:
            return '人群词'
        if word in self.word_lexicon['scene_words']:
            return '场景词'
        if word in self.word_lexicon['attribute_words'] or word.isdigit():
            return '属性词'
        if word in self._brand_token_set():
            return '品牌词'
        return '核心词'

    def _brand_token_set(self):
        if not hasattr(self, '_brand_tokens'):
            tokens = set()
            for i in range(1, 4):
                col = f'点击量最高的品牌 #{i}'
                if col not in self.df.columns:
                    continue
                series = self.df[col].dropna().astype(str).str.strip().str.lower()
                for brand in series[series != ''].unique():
                    if len(brand) >= 3:
                        tokens.add(brand)
            self._brand_tokens = tokens
        return self._brand_tokens

    # ------------------------------------------------------------------
    # 05 竞争格局分析（点击 TOP3 的 ASIN 层）
    # ------------------------------------------------------------------

    def _build_product_rows(self):
        rows = []
        for _, r in self.df.iterrows():
            for i in range(3):
                asin = r[self.ASIN_COLS[i]]
                if pd.isna(asin):
                    continue
                name_col = f'点击量最高的商品 #{i + 1}：商品名称'
                name = r.get(name_col)
                rows.append({
                    'ASIN': str(asin).strip().upper(),
                    '商品名称': (str(name)[:100] if pd.notna(name) else ''),
                    '点击份额': r[self.CLICK_COLS[i]],
                    '转化份额': r[self.CONV_COLS[i]],
                    '搜索词': r['搜索词'],
                    '期': r['期'],
                    '位次': i + 1,
                })
        self.product_df = pd.DataFrame(rows)
        return self.product_df

    def analyze_competition(self):
        print('\n📊 5/7 竞争格局分析（点击 TOP3 商品层）...')
        pdf = self._build_product_rows()
        if pdf.empty:
            print('   ⚠️ 无商品数据，跳过')
            return pd.DataFrame()

        agg = pdf.groupby('ASIN').agg(
            上榜次数=('搜索词', 'size'),
            覆盖搜索词数=('搜索词', 'nunique'),
            平均点击份额=('点击份额', 'mean'),
            平均转化份额=('转化份额', 'mean'),
            商品名称=('商品名称', 'first'),
        ).reset_index()
        agg['成交系数'] = np.where(
            (agg['平均点击份额'] > 0) & agg['平均转化份额'].notna(),
            agg['平均转化份额'] / agg['平均点击份额'], np.nan)
        agg['自家'] = agg['ASIN'].isin(self.own_asins).map({True: '★自家', False: ''})
        agg = agg.sort_values('上榜次数', ascending=False).reset_index(drop=True)
        agg.insert(0, '排名', agg.index + 1)
        agg = agg.round({'平均点击份额': 2, '平均转化份额': 2, '成交系数': 2})

        keep = pd.concat([agg.head(50), agg[agg['自家'] == '★自家']]).drop_duplicates(subset=['ASIN'])
        keep.to_csv(os.path.join(self.reports_dir, '05_竞争格局分析.csv'),
                    index=False, encoding='utf-8-sig')

        md_path = os.path.join(self.reports_dir, '05_竞争格局分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 竞争格局分析报告（点击 TOP3 商品层）\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            f.write('> ⚠️ **对象口径**：本表中的 ASIN 是各搜索词下**被点击最多**的商品（多为竞品，'
                    '自家 ASIN 已标 ★），点击含广告位；它们是"点击王"不必然是"转化王"。\n\n')
            top = agg.iloc[0]
            f.write('## 📊 数据事实：执行摘要\n\n')
            f.write(f"- **上榜最多商品**: {top['ASIN']}（{int(top['上榜次数'])} 次，"
                    f"覆盖 {int(top['覆盖搜索词数'])} 个搜索词）\n")
            f.write(f'- **总商品数**: {len(agg)}\n')
            n_own = int((agg['自家'] == '★自家').sum())
            f.write(f'- **自家 ASIN 上榜**: {n_own} 个\n\n')
            f.write('## 🏆 TOP 20 高频上榜商品\n\n')
            f.write('| 排名 | ASIN | 自家 | 商品名称 | 上榜次数 | 覆盖词数 | 平均点击份额 | 平均转化份额 | 成交系数 |\n')
            f.write('|---|---|---|---|---|---|---|---|---|\n')
            for _, r in agg.head(20).iterrows():
                name = r['商品名称'][:40] + ('...' if len(r['商品名称']) > 40 else '')
                f.write(f"| {r['排名']} | {r['ASIN']} | {r['自家']} | {name} | {int(r['上榜次数'])} | "
                        f"{int(r['覆盖搜索词数'])} | {_fmt(r['平均点击份额'])}% | "
                        f"{_fmt(r['平均转化份额'])}% | {_fmt(r['成交系数'])} |\n")
            f.write('\n## 💡 分析推断：攻防建议\n\n')
            rivals = agg[agg['自家'] == ''].head(3)
            if not rivals.empty:
                rivals_str = ', '.join(rivals['ASIN'])
                f.write(f'- **重点研究竞品**（{rivals_str}）：标题结构、主图、价格带、'
                        'A+ 与评论关注点，作为差异化基准\n')
            f.write('- **广告 ASIN 定向候选**：高上榜、成交系数 < 1 的竞品是截流首选（详见 06 成交系数分析）\n')
            f.write('- 自家 ASIN 若上榜：进入 03 报告的场景 A 状态跟踪（收割/漏水/预警）\n\n')
            f.write('---\n\n**数据说明**: 基于各搜索词点击 TOP3 位置统计；上榜次数为 词×期 粒度\n')

        print(f'   ✓ 分析 {len(agg)} 个商品 | 输出: 05_竞争格局分析.csv + .md')
        return agg

    # ------------------------------------------------------------------
    # 06 成交系数分析（per-ASIN，业内标准公式）
    # ------------------------------------------------------------------

    def analyze_coefficient(self, agg):
        print('\n📊 6/7 成交系数分析...')
        if agg is None or agg.empty:
            print('   ⚠️ 无商品数据，跳过')
            return pd.DataFrame()

        df = agg.copy()

        def classify(row):
            if pd.isna(row['成交系数']):
                return '数据不足'
            if row['成交系数'] >= self.th['coefficient_threshold']:
                return 'Closer（高于词均转化）'
            return '流量磁铁（低于词均转化）'

        df['系数分类'] = df.apply(classify, axis=1)
        df = df.sort_values('成交系数', ascending=False, na_position='last').reset_index(drop=True)
        df.insert(0, '系数排名', df.index + 1)
        out_cols = ['系数排名', 'ASIN', '自家', '商品名称', '上榜次数', '覆盖搜索词数',
                    '平均点击份额', '平均转化份额', '成交系数', '系数分类']
        # 自家 ASIN 无论系数排名如何都必须入 CSV
        keep = pd.concat([df.head(100), df[df['自家'] == '★自家']]).drop_duplicates(subset=['ASIN'])
        keep[out_cols].to_csv(os.path.join(self.reports_dir, '06_成交系数分析.csv'),
                              index=False, encoding='utf-8-sig')

        md_path = os.path.join(self.reports_dir, '06_成交系数分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 成交系数分析报告（ASIN 层）\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            f.write('**公式**：成交系数 = 转化份额 ÷ 点击份额 = 该 ASIN 转化率 ÷ 该词平均转化率。\n')
            f.write(f"≥ {self.th['coefficient_threshold']} = Closer（接得住流量）；"
                    '< 1 = 流量磁铁（拿点击不拿单）；转化数据缺失 = 数据不足（不判定）。\n\n')
            counts = df['系数分类'].value_counts()
            f.write('## 📊 数据事实：执行摘要\n\n')
            for k in ['Closer（高于词均转化）', '流量磁铁（低于词均转化）', '数据不足']:
                if counts.get(k, 0):
                    f.write(f'- **{k}**: {counts[k]} 个\n')
            f.write('\n')

            own = df[df['自家'] == '★自家']
            if not own.empty:
                f.write('## ★ 自家 ASIN 自诊\n\n')
                f.write('| ASIN | 平均点击份额 | 平均转化份额 | 成交系数 | 判定 |\n|---|---|---|---|---|\n')
                for _, r in own.iterrows():
                    f.write(f"| {r['ASIN']} | {_fmt(r['平均点击份额'])}% | {_fmt(r['平均转化份额'])}% | "
                            f"{_fmt(r['成交系数'])} | {r['系数分类']} |\n")
                f.write('\n- 系数 ≥ 1：转化力是优势，放量防守\n')
                f.write('- 系数 < 1：先修详情页（价格/评价/主图/A+）再抬价，用 SQP 定位漏斗卡点\n\n')

            leaky = df[(df['自家'] == '') & (df['系数分类'] == '流量磁铁（低于词均转化）')]
            if not leaky.empty:
                f.write('## 🎯 截流目标清单（竞品流量磁铁）\n\n')
                f.write('> 这些竞品在其上榜词拿到点击但接不住转化——用 SP/SD 商品定向 + 有竞争力的'
                        '价格/评价承接其外流转化。\n\n')
                f.write('| ASIN | 上榜次数 | 平均点击份额 | 平均转化份额 | 成交系数 |\n|---|---|---|---|---|\n')
                for _, r in leaky.head(10).iterrows():
                    f.write(f"| {r['ASIN']} | {int(r['上榜次数'])} | {_fmt(r['平均点击份额'])}% | "
                            f"{_fmt(r['平均转化份额'])}% | {_fmt(r['成交系数'])} |\n")
                f.write('\n')

            closers = df[(df['自家'] == '') & (df['系数分类'] == 'Closer（高于词均转化）')]
            if not closers.empty:
                f.write('## 📚 逆向学习对象（竞品 Closer）\n\n')
                f.write('> 这些竞品转化效率高于词均——研究其价格带、评论结构、主图与 A+，'
                        '找出让买家下单的要素。正面竞价其强势词需谨慎。\n\n')
                for _, r in closers.head(5).iterrows():
                    f.write(f"- **{r['ASIN']}**（系数 {_fmt(r['成交系数'])}）: {r['商品名称'][:60]}\n")
                f.write('\n')

            f.write('---\n\n**数据说明**:\n')
            f.write('- 成交系数基于跨期平均份额计算；单期低频词波动大，结论以多期复现为准\n')
            f.write('- "数据不足"多为转化分散/脱敏，不代表该 ASIN 无转化——用 SQP 或广告数据验证\n')

        print(f'   ✓ 系数分类完成 | 输出: 06_成交系数分析.csv + .md')
        return df

    # ------------------------------------------------------------------
    # 07 时间序列分析
    # ------------------------------------------------------------------

    def analyze_time_series(self):
        print('\n📊 7/7 时间序列分析...')
        periods = sorted(self.df['期'].unique())
        n_periods = len(periods)

        # 核心词 = 每一期都出现的搜索词
        term_periods = self.df.groupby('搜索词')['期'].nunique()
        core_terms = term_periods[term_periods == n_periods].index.tolist()

        stats = []
        for p in periods:
            sub = self.df[self.df['期'] == p]
            core_sub = sub[sub['搜索词'].isin(core_terms)]
            stats.append({
                '期': p,
                '搜索词数量': int(sub['搜索词'].nunique()),
                '核心词中位排名': _fmt_int(core_sub['搜索频率排名'].median()) if not core_sub.empty else '',
            })
        ts_df = pd.DataFrame(stats)
        ts_df.to_csv(os.path.join(self.reports_dir, '07_时间序列分析.csv'),
                     index=False, encoding='utf-8-sig')

        trend_df = pd.DataFrame()
        top_core = []
        if core_terms and n_periods >= 2:
            core_rank = {t: self.df[self.df['搜索词'] == t]['搜索频率排名'].mean() for t in core_terms}
            top_core = [t for t, _ in sorted(core_rank.items(), key=lambda x: x[1])[:10]]
            rows = []
            for t in top_core:
                sub = self.df[self.df['搜索词'] == t].sort_values('报告日期')
                for _, r in sub.iterrows():
                    rows.append({'搜索词': t, '期': r['期'], '搜索频率排名': r['搜索频率排名']})
            trend_df = pd.DataFrame(rows)
            trend_df.to_csv(os.path.join(self.reports_dir, '核心关键词趋势.csv'),
                            index=False, encoding='utf-8-sig')
            self._plot_core_trend(trend_df, top_core)

        md_path = os.path.join(self.reports_dir, '07_时间序列分析.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('# 时间序列分析报告\n\n')
            self._write_report_header(f)
            f.write('---\n\n')
            f.write('## 📊 数据事实：分期概览\n\n')
            f.write('| 期 | 搜索词数量 | 核心词中位排名 |\n|---|---|---|\n')
            for _, r in ts_df.iterrows():
                f.write(f"| {r['期']} | {r['搜索词数量']} | {r['核心词中位排名']} |\n")
            f.write('\n> ⚠️ "搜索词数量"反映报表导出范围而非市场大小；'
                    '季节性判断需**跨年同期**对比，单一时间窗内不下旺季/淡季结论。\n\n')

            if n_periods < 2:
                f.write('## 🔍 趋势分析\n\n- 仅 1 期数据，无法做趋势分析。'
                        '建议积累 ≥ 4 期（周报约 1 个月）后复跑。\n')
            else:
                f.write(f'## 🔍 核心关键词趋势（每期都出现的词，共 {len(core_terms)} 个）\n\n')
                if top_core:
                    f.write('TOP 10 核心词的首期 → 末期排名变化：\n\n')
                    f.write('| 搜索词 | 首期排名 | 末期排名 | 变化 |\n|---|---|---|---|\n')
                    for t in top_core:
                        sub = trend_df[trend_df['搜索词'] == t].sort_values('期')
                        first, last = sub.iloc[0]['搜索频率排名'], sub.iloc[-1]['搜索频率排名']
                        if pd.isna(first) or pd.isna(last):
                            continue
                        delta = int(first - last)
                        arrow = '↑ 热度上升' if delta > 0 else ('↓ 热度下降' if delta < 0 else '→ 持平')
                        f.write(f'| {t} | {int(first)} | {int(last)} | {arrow}（{delta:+d}）|\n')
                    f.write('\n详见 `核心关键词趋势.csv` / `核心关键词趋势.png`（排名越小越靠上）\n\n')
                f.write('## 💡 分析推断：实操建议\n\n')
                f.write('- 核心词排名持续上升（数字变小）→ 需求升温期，广告与库存提前联动\n')
                f.write('- 核心词排名持续下降 → 结合跨年同期数据判断是季节回落还是需求转移\n')
                f.write('- 关注新上榜高位词：可能是新场景/新竞品带起的需求，及时补进关键词库\n')
        print(f'   ✓ 分析 {n_periods} 期数据 | 输出: 07_时间序列分析.csv + .md')
        return ts_df

    def _plot_core_trend(self, trend_df, keywords):
        plt.figure(figsize=(14, 8))
        for kw in keywords:
            sub = trend_df[trend_df['搜索词'] == kw].sort_values('期')
            plt.plot(sub['期'], sub['搜索频率排名'], marker='o', label=kw, linewidth=2)
        plt.xlabel('期', fontsize=12)
        plt.ylabel('搜索频率排名（越小越热）', fontsize=12)
        plt.title('核心关键词搜索频率排名趋势', fontsize=14, fontweight='bold')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.gca().invert_yaxis()
        plt.tight_layout()
        plt.savefig(os.path.join(self.reports_dir, '核心关键词趋势.png'), dpi=300, bbox_inches='tight')
        plt.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_own_asins(args):
    asins = []
    if args.own_asins:
        asins += [a for a in re.split(r'[,\s]+', args.own_asins) if a]
    if args.own_asins_file:
        with open(args.own_asins_file, 'r', encoding='utf-8') as fh:
            asins += [line.strip() for line in fh if line.strip() and not line.startswith('#')]
    return asins


def main():
    parser = argparse.ArgumentParser(description='亚马逊 Brand Analytics 热门搜索词分析器 v3.0（场景化框架）')
    parser.add_argument('data_dir', nargs='?', default=os.getcwd(), help='Brand Analytics CSV 所在目录')
    parser.add_argument('--category-lexicon', help='可选品类词表 JSON（audience/scene/attribute_words 数组）')
    parser.add_argument('--own-asins', help='自家 ASIN，逗号分隔；提供后启用场景 A/B 路由')
    parser.add_argument('--own-asins-file', help='自家 ASIN 清单文件（每行一个，# 开头为注释）')
    parser.add_argument('--click-conc-scattered', type=float, default=DEFAULT_THRESHOLDS['click_conc_scattered'],
                        help='点击集中度：未整合市场上限（默认 30）')
    parser.add_argument('--click-conc-concentrated', type=float,
                        default=DEFAULT_THRESHOLDS['click_conc_concentrated'],
                        help='点击集中度：集中市场下限（默认 50）')
    parser.add_argument('--monopoly-redline', type=float, default=DEFAULT_THRESHOLDS['monopoly_redline'],
                        help='垄断红线：点击或转化集中度（默认 70）')
    parser.add_argument('--coefficient-threshold', type=float,
                        default=DEFAULT_THRESHOLDS['coefficient_threshold'],
                        help='成交系数/头部满足度分界（默认 1.0）')
    parser.add_argument('--own-gap-points', type=float, default=DEFAULT_THRESHOLDS['own_gap_points'],
                        help='自家漏水判定：点击-转化份额差（默认 4pt）')
    parser.add_argument('--sfr-tiers', default=','.join(str(x) for x in DEFAULT_THRESHOLDS['sfr_tiers']),
                        help='SFR 五级分层边界，默认 10000,20000,50000,100000')
    parser.add_argument('--bluesea-sfr', type=float, default=DEFAULT_THRESHOLDS['bluesea_sfr'],
                        help='蓝海信号 SFR 下限（默认 200000）')
    parser.add_argument('--bluesea-share', type=float, default=DEFAULT_THRESHOLDS['bluesea_share'],
                        help='蓝海信号份额下限（默认 60）')
    args = parser.parse_args()

    thresholds = {
        'click_conc_scattered': args.click_conc_scattered,
        'click_conc_concentrated': args.click_conc_concentrated,
        'monopoly_redline': args.monopoly_redline,
        'coefficient_threshold': args.coefficient_threshold,
        'own_gap_points': args.own_gap_points,
        'sfr_tiers': sorted(int(x) for x in args.sfr_tiers.split(',')),
        'bluesea_sfr': args.bluesea_sfr,
        'bluesea_share': args.bluesea_share,
    }

    print('=' * 60)
    print('🚀 亚马逊 Brand Analytics 热门搜索词分析器 v3.0')
    print('=' * 60)
    print(f'\n📁 数据目录: {args.data_dir}')

    analyzer = AmazonSearchAnalyzer(
        args.data_dir,
        category_lexicon=args.category_lexicon,
        own_asins=parse_own_asins(args),
        thresholds=thresholds,
    )
    if not analyzer.load_all_data():
        print('\n❌ 未找到有效的CSV文件')
        return
    analyzer.clean_data()

    print('\n' + '=' * 60)
    print('📊 开始 7 维度分析')
    print('=' * 60)

    analyzer.analyze_brands()
    analyzer.analyze_categories()
    analyzer.analyze_search_scenarios()
    analyzer.analyze_word_frequency()
    agg = analyzer.analyze_competition()
    analyzer.analyze_coefficient(agg)
    analyzer.analyze_time_series()

    print('\n' + '=' * 60)
    print('✅ 分析完成！')
    print('=' * 60)
    print(f'\n📊 报告目录: {analyzer.reports_dir}/')
    print('   1. 01_品牌竞争分析.csv + .md')
    print('   2. 02_类别趋势分析.csv + .md')
    print('   3. 03_搜索词热度分析.csv + .md（场景化分类核心产物）')
    print('   4. 04_词频统计分析.xlsx + .md')
    print('   5. 05_竞争格局分析.csv + .md')
    print('   6. 06_成交系数分析.csv + .md')
    print('   7. 07_时间序列分析.csv + .md（多期时含 核心关键词趋势.csv/.png）')


if __name__ == '__main__':
    main()
