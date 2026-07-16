"""Extended, source-backed visual catalog for the dashboard white paper.

The figures in this module are descriptive unless the caption explicitly says
that they are an adjusted estimate, sensitivity diagnostic, or predictive
explanation.  No chart introduces an estimand that is absent from the reviewed
analysis results.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from visual_semantics import (
    DESCRIPTIVE,
    GOOD,
    GOOD_GREEN,
    IMPROVE,
    IMPROVE_RED,
    MUTED_GRAY,
    NEUTRAL_BLUE,
    STATUS_COLORS,
    WATCH,
    WATCH_AMBER,
    classify_relative,
    colors_for,
    semantic_colorscale,
)


BLUE = NEUTRAL_BLUE
GOLD = WATCH_AMBER
INK = "#172033"
MUTED = "#64748B"
LIGHT = MUTED_GRAY


# Fifty-four figures, including the nine core causal/predictive figures created
# in reporting.py.  The sequence is also the white-paper reading order.
WHITEPAPER_CHART_SEQUENCE: list[dict[str, str]] = [
    {"section": "数据基础与运营全景", "key": "monthly_leads_orders", "caption": "月度线索与下订规模", "note": "月度规模图用于核对业务量级和时间覆盖，不用于推断策略效果。"},
    {"section": "数据基础与运营全景", "key": "business_funnel", "caption": "销售运营阶段规模", "note": "阶段规模用于展示线索、有效跟进、下订及无冲突订单的数量关系，各阶段口径并非严格同一时间漏斗。"},
    {"section": "数据基础与运营全景", "key": "monthly_conversion", "caption": "月度下订转化率", "note": "转化率按当月线索为分母，展示经营波动而非因果变化。"},
    {"section": "数据基础与运营全景", "key": "monthly_followup_coverage", "caption": "月度有效跟进覆盖率", "note": "有效跟进已排除入职前和交付后的异常事件。"},
    {"section": "数据基础与运营全景", "key": "city_leads", "caption": "城市线索规模", "note": "城市规模决定估计精度与运营容量，应与转化率分开解读。"},
    {"section": "数据基础与运营全景", "key": "city_conversion", "caption": "城市转化率", "note": "这是未调整的描述性转化率，不能直接解释为城市能力差异。"},
    {"section": "数据基础与运营全景", "key": "city_followup_coverage", "caption": "城市有效跟进覆盖率", "note": "覆盖率反映记录完整度和运营触达，不等于跟进的因果效果。"},
    {"section": "数据基础与运营全景", "key": "city_leads_orders", "caption": "城市线索与下订规模", "note": "城市线索量与下订量并列展示，便于区分规模贡献和转化效率。"},
    {"section": "数据基础与运营全景", "key": "city_coverage_conversion_scatter", "caption": "城市跟进覆盖率与转化率", "note": "城市聚合散点仅用于发现量效组合，不代表提高覆盖率必然带来转化提升。"},
    {"section": "客户与渠道结构", "key": "channel_lead_mix", "caption": "渠道线索规模", "note": "渠道规模用于描述获客结构，不能替代渠道贡献或投资回报率。"},
    {"section": "客户与渠道结构", "key": "channel_lead_share", "caption": "渠道线索份额", "note": "渠道份额描述获客结构集中度，不包含渠道费用或投资回报。"},
    {"section": "客户与渠道结构", "key": "channel_orders_per_100", "caption": "渠道每百线索订单数", "note": "每百线索订单数是转化效率指标，不是投资回报率。"},
    {"section": "客户与渠道结构", "key": "channel_followup_coverage", "caption": "渠道有效跟进覆盖率", "note": "跟进覆盖差异可能反映流程和记录差异，需结合样本量查看。"},
    {"section": "客户与渠道结构", "key": "age_conversion", "caption": "年龄段转化率", "note": "年龄段已分箱以降低重识别风险；结果仅作描述。"},
    {"section": "客户与渠道结构", "key": "gender_conversion", "caption": "性别转化率", "note": "性别差异未进行因果识别，不用于制定差别化待遇。"},
    {"section": "客户与渠道结构", "key": "first_method_mix", "caption": "首次有效跟进方式构成", "note": "同日多方式样本已标记为模糊处理，不强行归入面谈或非面谈。"},
    {"section": "客户与渠道结构", "key": "first_method_conversion", "caption": "首次跟进方式与转化率", "note": "首次跟进方式转化率是未调整描述，面谈的条件因果估计应以匹配和加权结果为准。"},
    {"section": "跟进过程与行为", "key": "method_duration", "caption": "有效跟进方式的沟通时长", "note": "图中同时展示中位数和均值，避免少量长通话主导解读。"},
    {"section": "跟进过程与行为", "key": "method_duration_boxplot", "caption": "跟进方式沟通时长分布", "note": "箱线图展示中位数和离散程度，极端长时沟通不应单独解释为更有效。"},
    {"section": "跟进过程与行为", "key": "followup_count_distribution", "caption": "线索有效跟进次数分布", "note": "跟进次数发生在处理后，只作过程描述，不进入倾向得分基线。"},
    {"section": "跟进过程与行为", "key": "followup_count_conversion", "caption": "有效跟进次数与转化率", "note": "跟进次数属于处理后变量，图中关系可能同时反映客户意向和销售投入。"},
    {"section": "跟进过程与行为", "key": "city_method_mix_heatmap", "caption": "城市跟进方式构成矩阵", "note": "矩阵展示各城市有效跟进记录中的方式占比，用于识别流程结构差异。"},
    {"section": "跟进过程与行为", "key": "testdrive_conversion", "caption": "试驾时长分组与转化率", "note": "试驾时长可能与意向共同决定，图表仅展示关联。"},
    {"section": "跟进过程与行为", "key": "city_channel_conversion_heatmap", "caption": "城市-渠道转化率矩阵", "note": "矩阵用于发现需要进一步诊断的组合，不用于预算自动分配。"},
    {"section": "跟进过程与行为", "key": "month_channel_conversion_heatmap", "caption": "月份-渠道转化率矩阵", "note": "同一渠道的月度变化可能同时受到客群和容量变化影响。"},
    {"section": "跟进过程与行为", "key": "city_month_leads_heatmap", "caption": "城市-月份线索量矩阵", "note": "线索量矩阵提供转化率的分母和运营负荷背景。"},
    {"section": "跟进过程与行为", "key": "city_month_conversion_heatmap", "caption": "城市-月份转化率矩阵", "note": "小样本波动应与同格线索量一起判断。"},
    {"section": "面谈跟进的因果证据", "key": "propensity", "caption": "倾向得分共同支持", "note": "共同支持存在是匹配可行性的必要条件，但不是效果成立的证明。"},
    {"section": "面谈跟进的因果证据", "key": "balance", "caption": "匹配前后协变量平衡", "note": "核心协变量匹配后绝对标准化均值差小于 0.1，平衡诊断通过。"},
    {"section": "面谈跟进的因果证据", "key": "effects", "caption": "两种方法的跟进效应估计", "note": "两种估计的置信区间均跨零，未发现可靠正向增益。"},
    {"section": "面谈跟进的因果证据", "key": "sensitivity", "caption": "隐藏偏差敏感性界限", "note": "敏感性分析用于说明未观测混杂可能如何改变匹配结论。"},
    {"section": "订单质量与交付风险", "key": "order_quality_flow", "caption": "订单质量筛选构成", "note": "关键冲突订单保留在审计中，但不进入主要交付估计。"},
    {"section": "订单质量与交付风险", "key": "order_conflict_types", "caption": "交付字段冲突数量", "note": "同一订单不同记录间字段不一致，是原始行直接汇总的主要风险。"},
    {"section": "订单质量与交付风险", "key": "temporal_issues", "caption": "异常时序审计", "note": "入职前、交付后跟进和首次同日多方式均被显式审计。"},
    {"section": "订单质量与交付风险", "key": "city_delay_rate", "caption": "城市延迟交付率", "note": "只使用无关键冲突订单，城市差异仍可能包含未观测交付复杂度。"},
    {"section": "订单质量与交付风险", "key": "city_delivery_score", "caption": "城市平均交付评分", "note": "评分按有效评分订单计算，并显示有效样本量。"},
    {"section": "订单质量与交付风险", "key": "city_complaint_rate", "caption": "城市投诉订单率", "note": "投诉率是无冲突订单中的描述性风险指标。"},
    {"section": "订单质量与交付风险", "key": "config_delay_rate", "caption": "配置延迟交付率", "note": "车型配置差异可能反映供应结构，不应直接归因于运营团队。"},
    {"section": "订单质量与交付风险", "key": "config_delivery_score", "caption": "配置平均交付评分", "note": "评分差异是描述性比较，未控制所有订单复杂度。"},
    {"section": "订单质量与交付风险", "key": "config_order_volume", "caption": "配置有效订单规模", "note": "配置订单量提供延迟率和评分比较的样本量背景。"},
    {"section": "订单质量与交付风险", "key": "config_complaint_rate", "caption": "配置投诉订单率", "note": "配置投诉率为无冲突订单中的描述性风险指标，不代表配置本身导致投诉。"},
    {"section": "订单质量与交付风险", "key": "monthly_delay_rate", "caption": "月度延迟交付率", "note": "月度趋势仅使用无冲突订单，分母随月份变化。"},
    {"section": "订单质量与交付风险", "key": "monthly_delivery_score", "caption": "月度平均交付评分", "note": "评分走势用于监控，不替代承诺与实际交付时间戳。"},
    {"section": "订单质量与交付风险", "key": "monthly_complaint_rate", "caption": "月度投诉订单率", "note": "投诉率走势用于风险监控，各月分母为无冲突有效订单。"},
    {"section": "订单质量与交付风险", "key": "delay_score_boxplot", "caption": "交付状态与评分分布", "note": "延迟与按时订单的评分分布比较未经完整混杂调整，只能作为描述性背景。"},
    {"section": "订单质量与交付风险", "key": "risk_scatter", "caption": "城市-月份延迟与投诉风险", "note": "散点关系是聚合关联，不是延迟导致投诉的识别结果。"},
    {"section": "订单质量与交付风险", "key": "delivery", "caption": "延迟交付调整后关联", "note": "评分结果跨零；投诉结果也只能报告为调整后关联。"},
    {"section": "渠道、预测与机会排序", "key": "channel", "caption": "渠道转化率及置信区间", "note": "威尔逊区间展示描述性转化率的不确定性。"},
    {"section": "渠道、预测与机会排序", "key": "channel_standardized", "caption": "渠道标准化边际转化率", "note": "标准化结果是调整后差异，不代表渠道因果贡献。"},
    {"section": "渠道、预测与机会排序", "key": "channel_raw_vs_standardized", "caption": "渠道原始与标准化转化率", "note": "原始和标准化差异可用于判断客群结构的影响，但仍不是多触点归因。"},
    {"section": "渠道、预测与机会排序", "key": "channel_standardization_gap", "caption": "渠道标准化前后差值", "note": "差值反映标准化调整对渠道转化率估计的影响，不代表渠道因果贡献。"},
    {"section": "渠道、预测与机会排序", "key": "importance", "caption": "时间外预测特征重要性", "note": "特征重要性解释预测模型，不代表因果贡献。"},
    {"section": "渠道、预测与机会排序", "key": "strategy", "caption": "城市-渠道机会优先级", "note": "优先级用于安排诊断和试验，不是预算投资回报率或预期增量订单。"},
    {"section": "渠道、预测与机会排序", "key": "opportunity_priority_scatter", "caption": "城市-渠道机会优先级矩阵", "note": "点的大小表示线索规模，颜色表示相对诊断优先级；该分数不是预算投资回报或预期增量订单。"},
]


def _save(fig: plt.Figure, chart_dir: Path, filename: str) -> Path:
    chart_dir.mkdir(parents=True, exist_ok=True)
    path = chart_dir / filename
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _clean_axis(ax, xlabel: str | None = None, ylabel: str | None = None) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.7, alpha=0.7)
    ax.set_axisbelow(True)
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)


def _add_action_legend(ax, include_baseline: bool = False) -> None:
    handles = [Patch(color=STATUS_COLORS[label], label=label) for label in (IMPROVE, WATCH, GOOD)]
    if include_baseline:
        handles.append(Line2D([0], [0], color=MUTED, linestyle="--", label="总体基准"))
    ax.legend(
        handles=handles,
        frameon=False,
        ncol=3,
        fontsize=8.5,
        loc="best",
    )


def _bar(
    frame: pd.DataFrame,
    category: str,
    value: str,
    title: str,
    ylabel: str,
    chart_dir: Path,
    filename: str,
    percent: bool = False,
    digits: int = 0,
    direction: str | None = None,
) -> Path:
    data = frame.sort_values(value, ascending=False)
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    bar_colors = colors_for(data[value], direction) if direction else [BLUE] * len(data)
    bars = ax.bar(data[category].astype(str), data[value], color=bar_colors, edgecolor="white", linewidth=0.7)
    ax.set_title(title)
    _clean_axis(ax, ylabel=ylabel)
    ax.tick_params(axis="x", rotation=25)
    labels = [f"{v:.1%}" if percent else f"{v:,.{digits}f}" for v in data[value]]
    ax.bar_label(bars, labels=labels, padding=3, fontsize=8.5, color=INK)
    if percent:
        ax.set_ylim(0, max(float(data[value].max()) * 1.22, 0.05))
    if direction:
        ax.legend(
            handles=[Patch(color=STATUS_COLORS[label], label=label) for label in (IMPROVE, WATCH, GOOD)],
            frameon=False,
            ncol=3,
            loc="upper right",
            fontsize=8.5,
        )
    return _save(fig, chart_dir, filename)


def _heatmap(
    frame: pd.DataFrame,
    index: str,
    columns: str,
    values: str,
    title: str,
    chart_dir: Path,
    filename: str,
    percent: bool = False,
    direction: str | None = None,
) -> Path:
    pivot = frame.pivot(index=index, columns=columns, values=values)
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    matrix = pivot.to_numpy(dtype=float)
    cmap = semantic_colorscale(direction) if direction else "Blues"
    if direction:
        from matplotlib.colors import LinearSegmentedColormap

        cmap = LinearSegmentedColormap.from_list("action_semantics", [item[1] for item in cmap])
    image = ax.imshow(matrix, aspect="auto", cmap=cmap)
    ax.set_title(title)
    ax.set_xticks(np.arange(len(pivot.columns)), pivot.columns.astype(str), rotation=35, ha="right")
    ax.set_yticks(np.arange(len(pivot.index)), pivot.index.astype(str))
    threshold = np.nanmean(matrix)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            if np.isnan(value):
                continue
            label = f"{value:.1%}" if percent else f"{value:,.0f}"
            ax.text(j, i, label, ha="center", va="center", fontsize=7.5, color="white" if value > threshold else INK)
    fig.colorbar(image, ax=ax, shrink=0.78)
    return _save(fig, chart_dir, filename)


def _group_metrics(frame: pd.DataFrame, group: str) -> pd.DataFrame:
    return frame.groupby(group, observed=True, as_index=False).agg(
        线索数=("线索ID", "nunique"),
        下订数=("是否下订", "sum"),
        转化率=("是否下订", "mean"),
        有效跟进覆盖率=("有效跟进线索", "mean"),
    )


def build_extended_charts(
    bundle: Any,
    analysis: dict[str, Any],
    chart_dir: Path,
    strategy: pd.DataFrame | None = None,
) -> dict[str, Path]:
    """Build the 45 descriptive figures that complement the nine core charts."""
    output: dict[str, Path] = {}
    leads = bundle.leads.copy()
    orders_all = bundle.orders.copy()
    orders = orders_all.loc[~orders_all["关键冲突"]].copy()
    followups = bundle.followups.loc[bundle.followups["有效跟进"]].copy()

    monthly = _group_metrics(leads, "月份").sort_values("月份")
    fig, ax = plt.subplots(figsize=(10, 5.3))
    ax.plot(monthly["月份"], monthly["线索数"], marker="o", color=BLUE, label="线索数")
    ax.plot(monthly["月份"], monthly["下订数"], marker="s", color=GOLD, label="下订数")
    ax.set_title("月度线索与下订规模")
    ax.tick_params(axis="x", rotation=35); ax.legend(frameon=False); _clean_axis(ax, ylabel="数量")
    output["monthly_leads_orders"] = _save(fig, chart_dir, "w5_10_monthly_leads_orders.png")

    funnel = pd.DataFrame({
        "阶段": ["全部线索", "有效跟进线索", "下订线索", "无冲突有效订单"],
        "数量": [
            leads["线索ID"].nunique(),
            int(leads["有效跟进线索"].sum()),
            int(leads["是否下订"].sum()),
            orders["订单ID"].nunique(),
        ],
    })
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    funnel_colors = [BLUE, "#60A5FA", GOLD, GOOD_GREEN]
    bars = ax.bar(funnel["阶段"], funnel["数量"], color=funnel_colors, edgecolor="white")
    ax.bar_label(bars, labels=[f"{v:,.0f}" for v in funnel["数量"]], padding=3, fontsize=9, color=INK)
    ax.set_title("销售运营阶段规模")
    _clean_axis(ax, ylabel="对象数量")
    output["business_funnel"] = _save(fig, chart_dir, "w5_41_business_funnel.png")

    fig, ax = plt.subplots(figsize=(10, 5.1))
    conversion_values = monthly["转化率"] * 100
    ax.plot(monthly["月份"], conversion_values, color=MUTED_GRAY, linewidth=1.8)
    ax.scatter(monthly["月份"], conversion_values, color=colors_for(conversion_values, "higher"), s=55, zorder=3)
    ax.axhline(leads["是否下订"].mean() * 100, color=MUTED, linestyle="--", label="总体")
    ax.set_title("月度下订转化率"); ax.tick_params(axis="x", rotation=35); _add_action_legend(ax, include_baseline=True)
    _clean_axis(ax, ylabel="转化率（%）")
    output["monthly_conversion"] = _save(fig, chart_dir, "w5_11_monthly_conversion.png")

    fig, ax = plt.subplots(figsize=(10, 5.1))
    coverage_values = monthly["有效跟进覆盖率"] * 100
    ax.plot(monthly["月份"], coverage_values, color=MUTED_GRAY, linewidth=1.8)
    ax.scatter(monthly["月份"], coverage_values, color=colors_for(coverage_values, "higher"), s=55, zorder=3)
    _add_action_legend(ax)
    ax.set_title("月度有效跟进覆盖率"); ax.tick_params(axis="x", rotation=35); _clean_axis(ax, ylabel="覆盖率（%）")
    output["monthly_followup_coverage"] = _save(fig, chart_dir, "w5_12_monthly_followup_coverage.png")

    city = _group_metrics(leads, "城市")
    output["city_leads"] = _bar(city, "城市", "线索数", "城市线索规模", "线索数", chart_dir, "w5_13_city_leads.png")
    output["city_conversion"] = _bar(city, "城市", "转化率", "城市转化率（描述性）", "转化率", chart_dir, "w5_14_city_conversion.png", percent=True, direction="higher")
    output["city_followup_coverage"] = _bar(city, "城市", "有效跟进覆盖率", "城市有效跟进覆盖率", "覆盖率", chart_dir, "w5_15_city_followup_coverage.png", percent=True, direction="higher")

    city_volume = city.sort_values("线索数", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 5.4))
    x = np.arange(len(city_volume)); width = 0.38
    ax.bar(x - width / 2, city_volume["线索数"], width, label="线索数", color=BLUE)
    ax.bar(x + width / 2, city_volume["下订数"], width, label="下订数", color=GOLD)
    ax.set_xticks(x, city_volume["城市"], rotation=25)
    ax.set_title("城市线索与下订规模")
    ax.legend(frameon=False)
    _clean_axis(ax, ylabel="数量")
    output["city_leads_orders"] = _save(fig, chart_dir, "w5_42_city_leads_orders.png")

    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    city_score = (city["有效跟进覆盖率"].rank(pct=True) + city["转化率"].rank(pct=True)) / 2
    city_sizes = 80 + 260 * city["线索数"] / city["线索数"].max()
    ax.scatter(
        city["有效跟进覆盖率"] * 100,
        city["转化率"] * 100,
        s=city_sizes,
        color=colors_for(city_score, "higher"),
        alpha=0.8,
        edgecolor="white",
        linewidth=0.8,
    )
    label_offsets = {
        "北京": (7, 12),
        "成都": (-42, -14),
        "西安": (7, -4),
    }
    for _, row in city.iterrows():
        offset = label_offsets.get(row["城市"], (5, 6))
        ax.annotate(
            row["城市"],
            (row["有效跟进覆盖率"] * 100, row["转化率"] * 100),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
            ha="right" if offset[0] < 0 else "left",
        )
    ax.set_title("城市有效跟进覆盖率与转化率")
    _add_action_legend(ax)
    _clean_axis(ax, xlabel="有效跟进覆盖率（%）", ylabel="转化率（%）")
    output["city_coverage_conversion_scatter"] = _save(fig, chart_dir, "w5_43_city_coverage_conversion_scatter.png")

    channel = _group_metrics(leads, "渠道")
    channel["每百线索订单数"] = channel["下订数"] / channel["线索数"] * 100
    output["channel_lead_mix"] = _bar(channel, "渠道", "线索数", "渠道线索规模", "线索数", chart_dir, "w5_16_channel_lead_mix.png")
    channel["线索份额"] = channel["线索数"] / channel["线索数"].sum()
    output["channel_lead_share"] = _bar(channel, "渠道", "线索份额", "渠道线索份额", "线索份额", chart_dir, "w5_44_channel_lead_share.png", percent=True)
    output["channel_followup_coverage"] = _bar(channel, "渠道", "有效跟进覆盖率", "渠道有效跟进覆盖率", "覆盖率", chart_dir, "w5_17_channel_followup_coverage.png", percent=True, direction="higher")
    output["channel_orders_per_100"] = _bar(channel, "渠道", "每百线索订单数", "渠道每百线索订单数（不是投资回报率）", "每百线索订单数", chart_dir, "w5_18_channel_orders_per_100.png", digits=1, direction="higher")

    age = _group_metrics(leads, "年龄段")
    gender = _group_metrics(leads, "客户性别")
    output["age_conversion"] = _bar(age, "年龄段", "转化率", "年龄段转化率（描述性）", "转化率", chart_dir, "w5_19_age_conversion.png", percent=True)
    output["gender_conversion"] = _bar(gender, "客户性别", "转化率", "性别转化率（描述性）", "转化率", chart_dir, "w5_20_gender_conversion.png", percent=True)

    method = leads["首次跟进方式"].fillna("无有效跟进").value_counts().rename_axis("首次跟进方式").reset_index(name="线索数")
    output["first_method_mix"] = _bar(method, "首次跟进方式", "线索数", "首次有效跟进方式构成", "线索数", chart_dir, "w5_21_first_method_mix.png")

    method_conversion = leads.assign(首次跟进方式展示=leads["首次跟进方式"].fillna("无有效跟进")).groupby("首次跟进方式展示", as_index=False).agg(
        线索数=("线索ID", "nunique"),
        转化率=("是否下订", "mean"),
    )
    output["first_method_conversion"] = _bar(
        method_conversion,
        "首次跟进方式展示",
        "转化率",
        "首次跟进方式与转化率（描述性）",
        "转化率",
        chart_dir,
        "w5_45_first_method_conversion.png",
        percent=True,
    )

    duration = followups.groupby("跟进方式", as_index=False).agg(平均沟通时长=("沟通时长(分钟)", "mean"), 中位沟通时长=("沟通时长(分钟)", "median"))
    duration = duration.sort_values("平均沟通时长", ascending=False)
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = np.arange(len(duration)); width = 0.36
    ax.bar(x - width/2, duration["平均沟通时长"], width, label="均值", color=BLUE)
    ax.bar(x + width/2, duration["中位沟通时长"], width, label="中位数", color=GOLD)
    ax.set_xticks(x, duration["跟进方式"]); ax.set_title("有效跟进方式的沟通时长"); ax.legend(frameon=False)
    _clean_axis(ax, ylabel="分钟")
    output["method_duration"] = _save(fig, chart_dir, "w5_22_method_duration.png")

    duration_groups = [group["沟通时长(分钟)"].dropna().to_numpy() for _, group in followups.groupby("跟进方式", observed=True)]
    duration_labels = [str(name) for name, _ in followups.groupby("跟进方式", observed=True)]
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    box = ax.boxplot(duration_groups, tick_labels=duration_labels, patch_artist=True, showfliers=False)
    for patch in box["boxes"]:
        patch.set_facecolor("#93C5FD"); patch.set_edgecolor(BLUE)
    for median in box["medians"]:
        median.set_color(GOLD); median.set_linewidth(2)
    ax.set_title("有效跟进方式的沟通时长分布")
    _clean_axis(ax, ylabel="沟通时长（分钟）")
    output["method_duration_boxplot"] = _save(fig, chart_dir, "w5_46_method_duration_boxplot.png")

    counts = leads["有效跟进次数"].clip(upper=6).value_counts().sort_index().rename_axis("次数").reset_index(name="线索数")
    counts["次数"] = counts["次数"].map(lambda x: "6+" if x == 6 else str(int(x)))
    output["followup_count_distribution"] = _bar(counts, "次数", "线索数", "线索有效跟进次数分布", "线索数", chart_dir, "w5_23_followup_count_distribution.png")

    leads["有效跟进次数段"] = leads["有效跟进次数"].clip(upper=6).map(lambda x: "6次及以上" if x == 6 else f"{int(x)}次")
    count_conversion = leads.groupby("有效跟进次数段", as_index=False).agg(线索数=("线索ID", "nunique"), 转化率=("是否下订", "mean"))
    count_order = {"0次": 0, "1次": 1, "2次": 2, "3次": 3, "4次": 4, "5次": 5, "6次及以上": 6}
    count_conversion["排序"] = count_conversion["有效跟进次数段"].map(count_order)
    count_conversion = count_conversion.sort_values("排序")
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    bars = ax.bar(count_conversion["有效跟进次数段"], count_conversion["转化率"] * 100, color=BLUE, edgecolor="white")
    ax.bar_label(bars, labels=[f"{v:.1%}" for v in count_conversion["转化率"]], padding=3, fontsize=8.5)
    ax.set_title("有效跟进次数与转化率（描述性）")
    _clean_axis(ax, xlabel="有效跟进次数", ylabel="转化率（%）")
    output["followup_count_conversion"] = _save(fig, chart_dir, "w5_47_followup_count_conversion.png")

    followups_with_city = followups.merge(leads[["线索ID", "城市"]], on="线索ID", how="left", validate="many_to_one")
    city_method = followups_with_city.groupby(["城市", "跟进方式"], as_index=False).size().rename(columns={"size": "跟进次数"})
    city_method["方式占比"] = city_method["跟进次数"] / city_method.groupby("城市")["跟进次数"].transform("sum")
    output["city_method_mix_heatmap"] = _heatmap(
        city_method,
        "城市",
        "跟进方式",
        "方式占比",
        "城市有效跟进方式构成矩阵",
        chart_dir,
        "w5_48_city_method_mix_heatmap.png",
        percent=True,
    )

    leads["试驾时长段"] = pd.cut(leads["试驾时长"], [-np.inf, 15, 30, 45, 60, np.inf], labels=["≤15", "16-30", "31-45", "46-60", ">60"])
    drive = _group_metrics(leads, "试驾时长段")
    output["testdrive_conversion"] = _bar(drive, "试驾时长段", "转化率", "试驾时长分组与转化率（描述性）", "转化率", chart_dir, "w5_24_testdrive_conversion.png", percent=True)

    cc = leads.groupby(["城市", "渠道"], as_index=False).agg(线索数=("线索ID", "nunique"), 转化率=("是否下订", "mean"))
    mc = leads.groupby(["月份", "渠道"], as_index=False).agg(线索数=("线索ID", "nunique"), 转化率=("是否下订", "mean"))
    cm = leads.groupby(["城市", "月份"], as_index=False).agg(线索数=("线索ID", "nunique"), 转化率=("是否下订", "mean"))
    output["city_channel_conversion_heatmap"] = _heatmap(cc, "城市", "渠道", "转化率", "城市-渠道转化率矩阵", chart_dir, "w5_25_city_channel_conversion_heatmap.png", percent=True, direction="higher")
    output["month_channel_conversion_heatmap"] = _heatmap(mc, "月份", "渠道", "转化率", "月份-渠道转化率矩阵", chart_dir, "w5_26_month_channel_conversion_heatmap.png", percent=True, direction="higher")
    output["city_month_leads_heatmap"] = _heatmap(cm, "城市", "月份", "线索数", "城市-月份线索量矩阵", chart_dir, "w5_27_city_month_leads_heatmap.png")
    output["city_month_conversion_heatmap"] = _heatmap(cm, "城市", "月份", "转化率", "城市-月份转化率矩阵", chart_dir, "w5_28_city_month_conversion_heatmap.png", percent=True, direction="higher")

    quality = pd.DataFrame({"订单状态": ["唯一订单", "无关键冲突", "关键冲突"], "订单数": [len(orders_all), len(orders), int(orders_all["关键冲突"].sum())]})
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    quality_bars = ax.bar(quality["订单状态"], quality["订单数"], color=[BLUE, GOOD_GREEN, IMPROVE_RED], edgecolor="white")
    ax.bar_label(quality_bars, labels=[f"{v:,.0f}" for v in quality["订单数"]], padding=3, fontsize=8.5, color=INK)
    ax.set_title("订单质量筛选构成"); _clean_axis(ax, ylabel="订单数")
    ax.legend(handles=[Patch(color=GOOD_GREEN, label="可进入主分析"), Patch(color=IMPROVE_RED, label="优先修复")], frameon=False)
    output["order_quality_flow"] = _save(fig, chart_dir, "w5_29_order_quality_flow.png")

    conflicts = pd.Series(bundle.audit["order_conflicts"], name="冲突订单数").rename_axis("字段").reset_index()
    conflicts["字段"] = conflicts["字段"].astype(str).str.replace("ID", "编号", regex=False)
    output["order_conflict_types"] = _bar(conflicts, "字段", "冲突订单数", "交付字段冲突数量", "订单数", chart_dir, "w5_30_order_conflict_types.png", direction="lower")
    temporal = pd.Series(bundle.audit["temporal_issues"], name="数量").rename_axis("问题").reset_index()
    temporal["问题"] = temporal["问题"].map({"followups_before_hire": "入职前跟进", "followups_after_delivery": "交付后跟进", "leads_with_ambiguous_first_day_method": "首次同日多方式", "orders_with_ticket_before_delivery": "工单早于交付"}).fillna(temporal["问题"])
    output["temporal_issues"] = _bar(temporal, "问题", "数量", "异常时序审计", "记录/对象数", chart_dir, "w5_31_temporal_issues.png", direction="lower")

    def order_group(group: str) -> pd.DataFrame:
        return orders.groupby(group, as_index=False).agg(
            有效订单数=("订单ID", "nunique"),
            延迟率=("是否延迟交付", "mean"),
            平均评分=("交付评分", "mean"),
            投诉订单率=("有投诉", "mean"),
        )

    order_city = order_group("城市")
    order_config = order_group("配置")
    order_config["配置展示"] = order_config["配置"].replace(
        {
            "725 Max": "725 高配版",
            "625 Max": "625 高配版",
            "680四驱Max": "680四驱高配版",
        }
    )
    order_month = order_group("交付月份").sort_values("交付月份")
    output["city_delay_rate"] = _bar(order_city, "城市", "延迟率", "城市延迟交付率（无冲突订单）", "延迟率", chart_dir, "w5_32_city_delay_rate.png", percent=True, direction="lower")
    output["city_delivery_score"] = _bar(order_city, "城市", "平均评分", "城市平均交付评分（无冲突订单）", "评分", chart_dir, "w5_33_city_delivery_score.png", digits=2, direction="higher")
    output["city_complaint_rate"] = _bar(order_city, "城市", "投诉订单率", "城市投诉订单率（无冲突订单）", "投诉订单率", chart_dir, "w5_34_city_complaint_rate.png", percent=True, direction="lower")
    output["config_delay_rate"] = _bar(order_config, "配置展示", "延迟率", "配置延迟交付率（无冲突订单）", "延迟率", chart_dir, "w5_35_config_delay_rate.png", percent=True, direction="lower")
    output["config_delivery_score"] = _bar(order_config, "配置展示", "平均评分", "配置平均交付评分（无冲突订单）", "评分", chart_dir, "w5_36_config_delivery_score.png", digits=2, direction="higher")
    output["config_order_volume"] = _bar(order_config, "配置展示", "有效订单数", "配置有效订单规模（无冲突订单）", "有效订单数", chart_dir, "w5_49_config_order_volume.png")
    output["config_complaint_rate"] = _bar(order_config, "配置展示", "投诉订单率", "配置投诉订单率（无冲突订单）", "投诉订单率", chart_dir, "w5_50_config_complaint_rate.png", percent=True, direction="lower")

    fig, ax = plt.subplots(figsize=(10, 5.1))
    delay_values = order_month["延迟率"] * 100
    ax.plot(order_month["交付月份"], delay_values, color=MUTED_GRAY, linewidth=1.8)
    ax.scatter(order_month["交付月份"], delay_values, color=colors_for(delay_values, "lower"), s=55, zorder=3)
    _add_action_legend(ax)
    ax.set_title("月度延迟交付率（无冲突订单）"); ax.tick_params(axis="x", rotation=35); _clean_axis(ax, ylabel="延迟率（%）")
    output["monthly_delay_rate"] = _save(fig, chart_dir, "w5_37_monthly_delay_rate.png")

    fig, ax = plt.subplots(figsize=(10, 5.1))
    score_values = order_month["平均评分"]
    ax.plot(order_month["交付月份"], score_values, color=MUTED_GRAY, linewidth=1.8)
    ax.scatter(order_month["交付月份"], score_values, color=colors_for(score_values, "higher"), s=55, zorder=3)
    _add_action_legend(ax)
    ax.set_title("月度平均交付评分（无冲突订单）"); ax.tick_params(axis="x", rotation=35); _clean_axis(ax, ylabel="评分")
    output["monthly_delivery_score"] = _save(fig, chart_dir, "w5_38_monthly_delivery_score.png")

    fig, ax = plt.subplots(figsize=(10, 5.1))
    complaint_values = order_month["投诉订单率"] * 100
    ax.plot(order_month["交付月份"], complaint_values, color=MUTED_GRAY, linewidth=1.8)
    ax.scatter(order_month["交付月份"], complaint_values, color=colors_for(complaint_values, "lower"), s=55, zorder=3)
    _add_action_legend(ax)
    ax.set_title("月度投诉订单率（无冲突订单）")
    ax.tick_params(axis="x", rotation=35)
    _clean_axis(ax, ylabel="投诉订单率（%）")
    output["monthly_complaint_rate"] = _save(fig, chart_dir, "w5_51_monthly_complaint_rate.png")

    delayed_mask = orders["是否延迟交付"].astype(bool)
    score_groups = [
        orders.loc[~delayed_mask, "交付评分"].dropna().to_numpy(),
        orders.loc[delayed_mask, "交付评分"].dropna().to_numpy(),
    ]
    fig, ax = plt.subplots(figsize=(8.8, 5.3))
    box = ax.boxplot(score_groups, tick_labels=["按时交付", "延迟交付"], patch_artist=True, showfliers=False)
    for patch, color in zip(box["boxes"], [GOOD_GREEN, WATCH_AMBER]):
        patch.set_facecolor(color); patch.set_alpha(0.65); patch.set_edgecolor(INK)
    for median in box["medians"]:
        median.set_color(INK); median.set_linewidth(2)
    ax.set_title("交付状态与交付评分分布")
    _clean_axis(ax, ylabel="交付评分")
    output["delay_score_boxplot"] = _save(fig, chart_dir, "w5_52_delay_score_boxplot.png")

    risk = orders.groupby(["城市", "交付月份"], as_index=False).agg(有效订单数=("订单ID", "nunique"), 延迟率=("是否延迟交付", "mean"), 投诉订单率=("有投诉", "mean"))
    fig, ax = plt.subplots(figsize=(9.5, 5.7))
    sizes = 30 + 220 * risk["有效订单数"] / risk["有效订单数"].max()
    risk_score = (risk["延迟率"].rank(pct=True) + risk["投诉订单率"].rank(pct=True)) / 2
    ax.scatter(risk["延迟率"] * 100, risk["投诉订单率"] * 100, s=sizes, alpha=0.72, color=colors_for(risk_score, "lower"), edgecolor="white", linewidth=0.7)
    _add_action_legend(ax)
    ax.set_title("城市-月份延迟与投诉风险（聚合关联）"); _clean_axis(ax, xlabel="延迟率（%）", ylabel="投诉订单率（%）")
    output["risk_scatter"] = _save(fig, chart_dir, "w5_39_risk_scatter.png")

    raw = pd.DataFrame(analysis["channel"]["descriptive"])[["渠道", "转化率"]].rename(columns={"转化率": "原始转化率"})
    std = pd.DataFrame(analysis["channel"]["standardized"])[["渠道", "标准化边际转化率"]]
    comp = raw.merge(std, on="渠道", how="inner").sort_values("原始转化率", ascending=False)
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = np.arange(len(comp)); width = 0.36
    ax.bar(x - width/2, comp["原始转化率"] * 100, width, label="原始", color=LIGHT)
    ax.bar(x + width/2, comp["标准化边际转化率"] * 100, width, label="标准化", color=BLUE)
    ax.set_xticks(x, comp["渠道"], rotation=25); ax.set_title("渠道原始与标准化转化率（关联性）"); ax.legend(frameon=False)
    _clean_axis(ax, ylabel="转化率（%）")
    output["channel_raw_vs_standardized"] = _save(fig, chart_dir, "w5_40_channel_raw_vs_standardized.png")

    comp["标准化差值"] = (comp["标准化边际转化率"] - comp["原始转化率"]) * 100
    gap = comp.sort_values("标准化差值")
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    gap_colors = ["#93C5FD" if value < 0 else GOLD for value in gap["标准化差值"]]
    bars = ax.barh(gap["渠道"], gap["标准化差值"], color=gap_colors, edgecolor="white")
    ax.axvline(0, color=INK, linewidth=0.9)
    ax.bar_label(bars, labels=[f"{v:+.2f}" for v in gap["标准化差值"]], padding=3, fontsize=8.5)
    ax.set_title("渠道标准化前后转化率差值")
    _clean_axis(ax, xlabel="标准化转化率减原始转化率（百分点）")
    output["channel_standardization_gap"] = _save(fig, chart_dir, "w5_53_channel_standardization_gap.png")

    if strategy is not None and not strategy.empty:
        opportunity = strategy.copy()
        fig, ax = plt.subplots(figsize=(10, 6.2))
        opportunity_status = classify_relative(opportunity["优先级分"], "lower")
        sizes = 35 + 260 * opportunity["线索数"] / opportunity["线索数"].max()
        ax.scatter(
            opportunity["转化率"] * 100,
            opportunity["优先级分"],
            s=sizes,
            color=[STATUS_COLORS[label] for label in opportunity_status],
            alpha=0.75,
            edgecolor="white",
            linewidth=0.7,
        )
        _add_action_legend(ax)
        ax.set_title("城市-渠道机会优先级矩阵")
        _clean_axis(ax, xlabel="转化率（%）", ylabel="机会优先级分")
        output["opportunity_priority_scatter"] = _save(fig, chart_dir, "w5_54_opportunity_priority_scatter.png")

    return output
