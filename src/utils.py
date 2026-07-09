"""
G9 智能销售运营决策系统 — 公共工具函数
"""
import pandas as pd
import numpy as np
import os
from config import *
import matplotlib.pyplot as plt
import seaborn as sns

# ═══════════════════════════════════════════════════════════════
# 颜色工具
# ═══════════════════════════════════════════════════════════════

def get_city_colors(cities):
    """为城市列表返回颜色映射"""
    return {c: CITY_COLORS.get(c, '#6B7280') for c in cities}

def get_channel_colors(channels):
    return {c: CHANNEL_COLORS.get(c, '#6B7280') for c in channels}

# ═══════════════════════════════════════════════════════════════
# 可视化辅助
# ═══════════════════════════════════════════════════════════════

def add_bar_labels(ax, fmt='{:.1f}', fontsize=8):
    """在柱状图上添加数值标签"""
    for bar in ax.patches:
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width()/2., h + h*0.01,
                    fmt.format(h), ha='center', va='bottom', fontsize=fontsize)

def add_significance_stars(ax, x1, x2, y, p_value):
    """在图上添加显著性标记"""
    stars = '***' if p_value < 0.001 else '**' if p_value < 0.01 else '*' if p_value < 0.05 else 'ns'
    if stars != 'ns':
        ax.plot([x1, x1, x2, x2], [y, y*1.02, y*1.02, y], 'k-', lw=1)
        ax.text((x1+x2)/2, y*1.03, stars, ha='center', fontsize=12)

# ═══════════════════════════════════════════════════════════════
# 统计分析
# ═══════════════════════════════════════════════════════════════

def cohens_d(group1, group2):
    """计算Cohen's d效应量"""
    n1, n2 = len(group1), len(group2)
    s1, s2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    s_pooled = np.sqrt(((n1-1)*s1 + (n2-1)*s2) / (n1+n2-2))
    return (np.mean(group1) - np.mean(group2)) / s_pooled

def bootstrap_ci(data, func=np.mean, n_bootstrap=1000, ci=95):
    """Bootstrap置信区间"""
    bootstraps = []
    n = len(data)
    rng = np.random.default_rng(SEED)
    for _ in range(n_bootstrap):
        sample = rng.choice(data, size=n, replace=True)
        bootstraps.append(func(sample))
    lower = (100 - ci) / 2
    upper = 100 - lower
    return np.percentile(bootstraps, [lower, upper])

def outlier_iqr(series, multiplier=1.5):
    """IQR法检测异常值"""
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - multiplier*iqr, q3 + multiplier*iqr
    return (series < lower) | (series > upper)

def outlier_zscore(series, threshold=3):
    """Z-Score法检测异常值"""
    z = np.abs((series - series.mean()) / series.std())
    return z > threshold

# ═══════════════════════════════════════════════════════════════
# 数据处理
# ═══════════════════════════════════════════════════════════════

def safe_median(group):
    """安全中位数，空组返回NaN"""
    return group.median() if len(group) > 0 else np.nan

def mode_or_first(series):
    """返回众数，多个众数时返回第一个"""
    modes = series.mode()
    return modes.iloc[0] if len(modes) > 0 else series.iloc[0] if len(series) > 0 else np.nan

def print_df_stats(df, name='DataFrame'):
    """打印DataFrame基本信息"""
    print(f'\n{"="*60}')
    print(f'  {name}: {df.shape[0]:,} 行 × {df.shape[1]} 列')
    print(f'{"="*60}')
    print(f'  内存: {df.memory_usage(deep=True).sum()/1024/1024:.1f} MB')
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100)
    for col in df.columns:
        m = missing[col]
        if m > 0:
            print(f'  ⚠ {col}: {m:,} 缺失 ({missing_pct[col]:.1f}%)')
    print(f'  数据类型分布:')
    for dtype in df.dtypes.value_counts().index:
        count = df.dtypes.value_counts()[dtype]
        print(f'    {dtype}: {count} 列')

print('✅ 工具模块加载完成')
