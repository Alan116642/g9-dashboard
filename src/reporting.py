"""Generate source-backed charts, notebooks, Word/PDF-ready reports, and W5 copy."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat as nbf
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from g9_pipeline import CHART_DIR, PRIVATE_DIR, REPORTS_DIR, ROOT, CleanBundle, json_ready
from visual_catalog import WHITEPAPER_CHART_SEQUENCE, build_extended_charts
from visual_semantics import (
    GOOD,
    GOOD_GREEN,
    IMPROVE,
    IMPROVE_RED,
    MUTED_GRAY,
    NEUTRAL_BLUE,
    STATUS_COLORS,
    WATCH,
    WATCH_AMBER,
    colors_for,
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

BLUE = NEUTRAL_BLUE.lstrip("#")
DARK_BLUE = "1F4D78"
INK = "172033"
MUTED = "64748B"
LIGHT = "F2F4F7"
GOLD = WATCH_AMBER.lstrip("#")


def _save(fig: plt.Figure, name: str) -> Path:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / name
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def build_charts(charts: dict[str, pd.DataFrame], bundle: CleanBundle, analysis: dict[str, Any]) -> dict[str, Path]:
    output: dict[str, Path] = {}
    colors = {"首次面谈": "#D97706", "其他方式": "#2563EB"}

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for label, group in charts["propensity"].groupby("处理组"):
        ax.hist(group["倾向得分"], bins=35, alpha=0.55, density=True, color=colors[label], label=f"{label} (n={len(group):,})")
    ax.set(title="倾向得分共同支持", xlabel="倾向得分", ylabel="密度")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    output["propensity"] = _save(fig, "w2_01_propensity_overlap.png")

    balance = charts["balance"].copy()
    balance["排序"] = balance[["匹配前SMD", "匹配后SMD"]].abs().max(axis=1)
    balance = balance.sort_values("排序").tail(18)
    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(balance))
    ax.scatter(balance["匹配前SMD"].abs(), y, label="匹配前", color="#94A3B8", s=40)
    ax.scatter(balance["匹配后SMD"].abs(), y, label="匹配后（通过）", color=GOOD_GREEN, s=45)
    ax.axvline(0.1, color=IMPROVE_RED, linestyle="--", linewidth=1.3, label="需改进阈值 |SMD|=0.1")
    ax.set_yticks(y, balance["协变量"]); ax.set(xlabel="绝对标准化均值差", title="匹配前后协变量平衡")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    output["balance"] = _save(fig, "w2_02_love_plot.png")

    effects = charts["effects"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    y = np.arange(len(effects))
    ax.errorbar(effects["估计"], y, xerr=[effects["估计"] - effects["下限"], effects["上限"] - effects["估计"]], fmt="o", color=WATCH_AMBER, ecolor=MUTED_GRAY, capsize=5, label="需要关注：区间跨零")
    ax.axvline(0, color="#111827", linestyle="--", linewidth=1)
    ax.set_yticks(y, effects["方法"]); ax.set(xlabel="下订概率差", title="跟进方式效应估计与 95% 置信区间")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    output["effects"] = _save(fig, "w2_03_followup_effects.png")

    sensitivity = charts["sensitivity"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(sensitivity["Gamma"], sensitivity["p值上界"], color="#2563EB", linewidth=2.2)
    ax.axhline(0.05, color="#B91C1C", linestyle="--", linewidth=1.2)
    ax.set(xlabel="隐藏偏差赔率上界 Γ", ylabel="双侧 p 值上界", title="匹配对隐藏偏差敏感性")
    ax.set_ylim(0, 1.02); ax.spines[["top", "right"]].set_visible(False)
    output["sensitivity"] = _save(fig, "w2_04_rosenbaum_bounds.png")

    delivery = charts["delivery"]
    score_rows = delivery.loc[delivery["结果"].str.startswith("评分")].copy()
    complaint_rows = delivery.loc[delivery["结果"].str.startswith("投诉")].copy()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, frame, title, xlabel, scale in [
        (axes[0], score_rows, "交付评分差异", "评分差异（分）", 1.0),
        (axes[1], complaint_rows, "投诉概率调整后关联", "概率差异（百分点）", 100.0),
    ]:
        y = np.arange(len(frame))
        estimate = (frame["估计"] * scale).to_numpy(dtype=float)
        lower = (frame["下限"] * scale).to_numpy(dtype=float)
        upper = (frame["上限"] * scale).to_numpy(dtype=float)
        ax.errorbar(estimate, y, xerr=[estimate - lower, upper - estimate], fmt="o", color=WATCH_AMBER, ecolor=MUTED_GRAY, capsize=5)
        ax.axvline(0, color="#111827", linestyle="--", linewidth=1)
        ax.set_yticks(y, frame["结果"]); ax.set(xlabel=xlabel, title=title)
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(handles=[Patch(color=WATCH_AMBER, label="需要关注：置信区间跨零")], frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.94))
    fig.suptitle("延迟交付与结果变量的估计（不同单位分面展示）")
    fig.tight_layout()
    output["delivery"] = _save(fig, "w2_05_delivery_associations.png")

    channel = charts["channel_descriptive"].sort_values("转化率")
    fig, ax = plt.subplots(figsize=(9, 5))
    channel_colors = colors_for(channel["转化率"], "higher")
    for idx, (_, row) in enumerate(channel.iterrows()):
        ax.errorbar(
            row["转化率"] * 100,
            idx,
            xerr=[[max(0.0, (row["转化率"] - row["置信区间下限"]) * 100)], [max(0.0, (row["置信区间上限"] - row["转化率"]) * 100)]],
            fmt="o",
            color=channel_colors[idx],
            ecolor=MUTED_GRAY,
            capsize=4,
        )
    ax.set_yticks(np.arange(len(channel)), channel["渠道"]); ax.set(xlabel="转化率（%）", title="渠道转化率及 Wilson 95% 置信区间")
    ax.legend(handles=[Patch(color=STATUS_COLORS[label], label=label) for label in (IMPROVE, WATCH, GOOD)], frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    output["channel"] = _save(fig, "w2_06_channel_conversion.png")

    standardized = charts["channel_standardized"].sort_values("标准化边际转化率")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(standardized["渠道"], standardized["标准化边际转化率"] * 100, color=colors_for(standardized["标准化边际转化率"], "higher"))
    ax.set(xlabel="标准化边际转化率（%）", title="渠道调整后边际转化率（关联性）")
    ax.legend(handles=[Patch(color=STATUS_COLORS[label], label=label) for label in (IMPROVE, WATCH, GOOD)], frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    output["channel_standardized"] = _save(fig, "w2_07_channel_standardized.png")

    importance = charts["model_importance"].sort_values("预测重要性")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(importance["特征"], importance["预测重要性"], color=["#2563EB" if v >= 0 else "#CBD5E1" for v in importance["预测重要性"]])
    ax.axvline(0, color="#111827", linewidth=0.8)
    ax.set(xlabel="时间外 ROC AUC 置换变化", title="基线预测特征重要性（非因果）")
    ax.spines[["top", "right"]].set_visible(False)
    output["importance"] = _save(fig, "w3_01_predictive_importance.png")

    strategy = charts["strategy"].head(12).sort_values("优先级分")
    labels = strategy["城市"] + " / " + strategy["渠道"]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, strategy["优先级分"], color=colors_for(strategy["优先级分"], "lower"))
    ax.set(xlabel="机会优先级分（非预算 ROI）", title="城市 × 渠道运营机会排序")
    ax.legend(handles=[Patch(color=STATUS_COLORS[label], label=label) for label in (IMPROVE, WATCH, GOOD)], frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    output["strategy"] = _save(fig, "w4_01_opportunity_priority.png")

    output.update(build_extended_charts(bundle, analysis, CHART_DIR))

    chart_map = {
        key: {
            "path": str(path.relative_to(ROOT)),
            "source": "data/processed/analysis_results.json and derived private aggregates",
            "purpose": key,
            "palette_policy": (
                "red=优先改进; amber=需要关注; green=表现较好; "
                "blue/gray=描述性或不可判优劣; 红橙绿为图内相对分位，非目标、显著性或因果效应"
            ),
        }
        for key, path in output.items()
    }
    for position, spec in enumerate(WHITEPAPER_CHART_SEQUENCE, start=1):
        chart_map[spec["key"]].update({
            "whitepaper_order": position,
            "section": spec["section"],
            "caption": spec["caption"],
            "interpretation": spec["note"],
        })
    (REPORTS_DIR / "chart_map.json").write_text(json.dumps(chart_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar"); tcPr.append(tcMar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}"); tcMar.append(node)
        node.set(qn("w:w"), str(value)); node.set(qn("w:type"), "dxa")


def _set_table_geometry(table, widths: list[int]) -> None:
    table.autofit = False; table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tblPr = table._tbl.tblPr
    tblW = tblPr.first_child_found_in("w:tblW")
    if tblW is None:
        tblW = OxmlElement("w:tblW"); tblPr.append(tblW)
    tblW.set(qn("w:w"), str(sum(widths))); tblW.set(qn("w:type"), "dxa")
    tblInd = tblPr.first_child_found_in("w:tblInd")
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd"); tblPr.append(tblInd)
    tblInd.set(qn("w:w"), "120"); tblInd.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid): grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol"); col.set(qn("w:w"), str(width)); grid.append(col)
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            tcW = cell._tc.get_or_add_tcPr().get_or_add_tcW(); tcW.set(qn("w:w"), str(width)); tcW.set(qn("w:type"), "dxa")
            _set_cell_margins(cell); cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _set_run(run, size=11, bold=False, color=INK, font="Calibri", italic=False):
    run.font.name = font; run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), font); run._element.rPr.rFonts.set(qn("w:hAnsi"), font)
    run.font.size = Pt(size); run.bold = bold; run.italic = italic; run.font.color.rgb = RGBColor.from_string(color)


def _page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 "); _set_run(run, size=9, color=MUTED)
    fld = OxmlElement("w:fldSimple"); fld.set(qn("w:instr"), "PAGE"); paragraph._p.append(fld)
    run2 = paragraph.add_run(" 页"); _set_run(run2, size=9, color=MUTED)


def _setup_doc(title: str, subtitle: str, report_type: str) -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5); section.page_height = Inches(11)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Inches(1)
    section.header_distance = section.footer_distance = Inches(0.492)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"; normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri"); normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11); normal.paragraph_format.space_after = Pt(6); normal.paragraph_format.line_spacing = 1.10
    for style_name, size, color, before, after in (("Heading 1",16,BLUE,16,8),("Heading 2",13,BLUE,12,6),("Heading 3",12,DARK_BLUE,8,4)):
        style = doc.styles[style_name]; style.font.name = "Calibri"; style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri"); style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size); style.font.bold = True; style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before); style.paragraph_format.space_after = Pt(after)
    header = section.header.paragraphs[0]; header.clear(); header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _set_run(header.add_run(report_type), size=9, bold=True, color=MUTED)
    footer = section.footer.paragraphs[0]; footer.clear(); _page_number(footer)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(4)
    _set_run(p.add_run(report_type.upper()), size=11, bold=True, color=GOLD)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(5)
    _set_run(p.add_run(title), size=23, bold=True, color="000000")
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(14)
    _set_run(p.add_run(subtitle), size=14, color="374151")
    for label, value in (("对象", "G9 销售运营决策团队"), ("数据截止", "2025-12-31（交付数据延伸至 2026-02-27）"), ("证据原则", "不以显著性为目标；诊断失败即降级结论")):
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(2)
        _set_run(p.add_run(f"{label}："), bold=True, color="000000"); _set_run(p.add_run(value), color="000000")
    doc.add_paragraph()
    return doc


def _add_bullets(doc: Document, items: list[str]):
    for item in items:
        p = doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after = Pt(6); p.paragraph_format.left_indent = Inches(0.5); p.paragraph_format.first_line_indent = Inches(-0.25)
        _set_run(p.add_run(item), color="111827")


def _add_image(doc: Document, path: Path, caption: str):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Inches(6.15))
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER; cap.paragraph_format.space_after = Pt(8)
    _set_run(cap.add_run(caption), size=9, color=MUTED, italic=True)


def _add_result_table(doc: Document, rows: list[list[str]]):
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    headers = ["分析", "估计", "95% 置信区间", "证据等级"]
    for i, value in enumerate(headers):
        cell = table.rows[0].cells[i]; cell.text = value
        cell._tc.get_or_add_tcPr().append(OxmlElement("w:shd")); cell._tc.tcPr[-1].set(qn("w:fill"), LIGHT)
        for run in cell.paragraphs[0].runs: _set_run(run, size=10, bold=True, color="111827")
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = value
            for run in cells[i].paragraphs[0].runs: _set_run(run, size=9.5, color="111827")
    _set_table_geometry(table, [2200, 1500, 2700, 2960])
    doc.add_paragraph()


def _add_color_legend(doc: Document) -> None:
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(8)
    _set_run(p.add_run("■ 优先改进  "), size=10, bold=True, color=IMPROVE_RED.lstrip("#"))
    _set_run(p.add_run("■ 需要关注  "), size=10, bold=True, color=WATCH_AMBER.lstrip("#"))
    _set_run(p.add_run("■ 表现较好  "), size=10, bold=True, color=GOOD_GREEN.lstrip("#"))
    _set_run(p.add_run("■ 描述性/不可判优劣"), size=10, bold=True, color=NEUTRAL_BLUE.lstrip("#"))
    p = doc.add_paragraph()
    _set_run(p.add_run("红橙绿按同一张图中的相对分位识别改进优先级，不是业务目标、显著性或因果效应；蓝灰图只用于描述结构。"), size=9.5, color=MUTED)


def _pp(value: float | None) -> str:
    return "不可估计" if value is None else f"{value * 100:+.2f} 个百分点"


def _ci_pp(ci: list[float | None]) -> str:
    if ci[0] is None: return "不可估计"
    return f"{ci[0] * 100:+.2f} 至 {ci[1] * 100:+.2f} 个百分点"


def generate_w2_docx(analysis: dict[str, Any], audit: dict[str, Any], images: dict[str, Path]) -> Path:
    psm = analysis["psm"]["psm_att"]; aipw = analysis["psm"]["aipw_att"]
    score = analysis["delivery"]["delivery_score_adjusted_association"]; complaint = analysis["delivery"]["complaint_adjusted_association"]
    doc = _setup_doc("G9 因果归因与证据审计", "跟进方式、交付延迟与渠道差异的重新分析", "W2 分析报告")
    doc.add_heading("Executive Summary", level=1)
    _add_bullets(doc, [
        f"匹配后协变量平衡通过，但首次面谈的 ATT 为 {_pp(psm['estimate'])}，95% CI 为 {_ci_pp(psm['ci95'])}；未发现可靠的转化增益证据。",
        f"AIPW 稳健性结果为 {_pp(aipw['estimate'])}，置信区间同样跨零，方向与 PSM 不构成可行动的正向证据。",
        f"延迟交付与交付评分的调整后差异为 {score['estimate']:+.3f} 分，95% CI {score['ci95'][0]:+.3f} 至 {score['ci95'][1]:+.3f}；不能支持评分存在显著下降。",
        "当前数据没有合法 RDD 断点，也没有多触点渠道路径或渠道级花费；RDD、Shapley 多触点归因及渠道 ROI 均不具备识别条件。",
    ])
    doc.add_heading("交付数据需要先修复粒度", level=1)
    p = doc.add_paragraph(); _set_run(p.add_run(f"5,000 条交付记录仅对应 {audit['row_counts']['unique_orders']:,} 个唯一订单；{audit['critical_conflict_orders']:,} 个订单存在关键字段冲突。主要交付分析仅使用 {audit['usable_orders']:,} 个无关键冲突订单。"))
    doc.add_heading("面谈跟进没有可靠的正向增益证据", level=1)
    _add_result_table(doc, [["PSM ATT", _pp(psm["estimate"]), _ci_pp(psm["ci95"]), psm["evidence_level"]], ["AIPW ATT", _pp(aipw["estimate"]), _ci_pp(aipw["ci95"]), aipw["evidence_level"]]])
    p = doc.add_paragraph(); _set_run(p.add_run(f"共匹配 {analysis['psm']['diagnostics']['matched_pairs']:,} 对线索；匹配后最大绝对 SMD 为 {analysis['psm']['diagnostics']['max_abs_smd_after']:.3f}。平衡达标只说明观察协变量更可比，不会把跨零结果变成显著效果。"))
    _add_image(doc, images["propensity"], "图 1. 倾向得分共同支持")
    _add_image(doc, images["balance"], "图 2. 匹配前后协变量平衡")
    _add_image(doc, images["effects"], "图 3. PSM 与 AIPW 效应估计")
    _add_image(doc, images["sensitivity"], "图 4. 匹配对隐藏偏差敏感性")
    doc.add_heading("延迟交付只能做调整后关联分析", level=1)
    p = doc.add_paragraph(); _set_run(p.add_run("评分模型控制城市、配置和交付月份，并采用 HC3 稳健标准误。评分差异置信区间跨零，因此不能得出负向影响；投诉结果虽出现统计关联，但经 FDR 后仍只能作为非因果线索，需补充承诺交付日、实际交付日和延迟原因。"))
    _add_result_table(doc, [["评分调整后关联", f"{score['estimate']:+.3f} 分", f"{score['ci95'][0]:+.3f} 至 {score['ci95'][1]:+.3f}", score["evidence_level"]], ["投诉概率调整后关联", _pp(complaint["estimate"]), _ci_pp(complaint["ci95"]), complaint["evidence_level"]]])
    _add_image(doc, images["delivery"], "图 5. 延迟交付与评分/投诉的调整后关联")
    doc.add_heading("RDD 可行性审计：不满足识别条件", level=1)
    _add_bullets(doc, ["没有连续分配变量及事先确定的阈值。", "交付里程中位数不是延迟交付的业务规则，不能被用作断点。", "因此不再生成 McCrary、带宽稳健性或安慰剂 RDD 结论。"])
    doc.add_heading("渠道输出改为描述和标准化关联", level=1)
    p = doc.add_paragraph(); _set_run(p.add_run("每条线索只有一个获客渠道，无法计算多触点 Shapley；市场费用只到城市-月份粒度，也无法计算渠道 ROI。报告保留渠道转化率及标准化边际转化率，并明确标注为关联性结果。"))
    _add_image(doc, images["channel"], "图 6. 渠道转化率及 95% 置信区间")
    _add_image(doc, images["channel_standardized"], "图 7. 渠道标准化边际转化率")
    doc.add_heading("Recommended Next Steps", level=1)
    _add_bullets(doc, ["补采下订时间戳，保证处理先于结果。", "补采承诺交付日、实际交付日及延迟原因，重新设计交付效果识别。", "补采渠道级花费和多触点路径后，再启用 ROI 或 Shapley。", "在面谈策略上优先进行随机或准随机试验，不以当前跨零估计作为扩张依据。"])
    doc.add_heading("Further Questions", level=1)
    _add_bullets(doc, ["首次跟进方式是否由销售员自主选择，还是由门店规则分配？", "下订发生在首次跟进之前的比例是多少？", "冲突交付记录来自更新历史、系统合并还是数据生成逻辑？"])
    doc.add_heading("Caveats and Assumptions", level=1)
    _add_bullets(doc, psm["assumptions"] + score["assumptions"])
    path = REPORTS_DIR / "W2_causal_attribution_report.docx"; doc.save(path); return path


def generate_whitepaper(analysis: dict[str, Any], audit: dict[str, Any], images: dict[str, Path], strategy: pd.DataFrame) -> tuple[Path, Path]:
    psm = analysis["psm"]["psm_att"]; model = analysis["model"]["metrics"]
    doc = _setup_doc("G9 销售运营证据白皮书", "从数据质量、因果识别到可执行运营验证", "W5 白皮书")
    doc.add_heading("Executive Summary", level=1)
    _add_bullets(doc, [
        "当前最重要的改进不是扩大某个渠道或跟进方式，而是先修复交付粒度并补齐关键时间戳。",
        f"首次面谈 ATT 为 {_pp(psm['estimate'])}，置信区间跨零；策略页不再把面谈写成确定性增益。",
        f"时间外预测 ROC AUC 为 {model['roc_auc']:.3f}，接近随机水平；公开看板关闭逐客户预测，本地模型仅保留为验证基线。",
        "渠道费用无法分配到渠道，预算建议已替换为基于规模、转化、跟进覆盖和机会量的优先级排序。",
    ])
    doc.add_heading("如何阅读这 40 张图", level=1)
    p = doc.add_paragraph(); _set_run(p.add_run(f"交付表中 {audit['critical_conflict_orders']:,}/{audit['row_counts']['unique_orders']:,} 个唯一订单存在关键字段冲突。图表按描述性运营、因果诊断、调整后关联、预测解释和机会排序分层；每张图旁均标明其可支持与不可支持的解释。"))
    _add_color_legend(doc)
    current_section = None
    for figure_no, spec in enumerate(WHITEPAPER_CHART_SEQUENCE, start=1):
        if spec["section"] != current_section:
            current_section = spec["section"]
            doc.add_heading(current_section, level=1)
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(4)
        _set_run(p.add_run(spec["note"]), size=10.5, color="111827")
        _add_image(doc, images[spec["key"]], f"图 {figure_no}. {spec['caption']}")

    doc.add_heading("运营机会排序明细", level=1)
    rows = []
    for _, row in strategy.head(8).iterrows():
        rows.append([f"{row['城市']} / {row['渠道']}", f"{row['线索数']:,}", f"{row['转化率']:.1%}", row["建议"]])
    table = doc.add_table(rows=1, cols=4); table.style = "Table Grid"
    for i, value in enumerate(["城市 / 渠道", "线索数", "转化率", "建议"]):
        table.rows[0].cells[i].text = value
        for run in table.rows[0].cells[i].paragraphs[0].runs: _set_run(run, size=10, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = value
            for run in cells[i].paragraphs[0].runs: _set_run(run, size=9)
    _set_table_geometry(table, [2300, 1300, 1500, 4260])
    doc.add_heading("90 天实施路径", level=1)
    _add_bullets(doc, ["0-30 天：锁定线索、订单、跟进事件唯一键和时间戳口径。", "31-60 天：开展跟进方式随机化试点，建立渠道花费明细。", "61-90 天：按实验结果更新策略规则，并将证据等级接入月度经营复盘。"])
    doc.add_heading("Further Questions", level=1)
    _add_bullets(doc, ["哪些指标可以由业务系统直接补采，而无需人工维护？", "策略试验的最小可检测效果和样本量应如何设置？", "渠道成本应按线索、曝光还是订单进行归属？"])
    doc.add_heading("Caveats and Assumptions", level=1)
    _add_bullets(doc, ["公开看板使用样本量阈值为 10 的脱敏汇总数据。", "预测重要性不是因果贡献。", "机会优先级不是预算 ROI，也不等于预期增量订单。", "原始 Excel 未被修改。"])
    docx_path = REPORTS_DIR / "W5_sales_operations_white_paper.docx"; doc.save(docx_path)

    md = ["# G9 销售运营证据白皮书", "", "## Executive Summary", "", f"- 面谈 ATT：{_pp(psm['estimate'])}，95% CI {_ci_pp(psm['ci95'])}，未发现可靠增益。", f"- 时间外 ROC AUC：{model['roc_auc']:.3f}，公开看板不提供逐客户预测。", "- RDD、多触点 Shapley 和渠道 ROI 均因数据条件不足而停用。", f"- 白皮书包含 {len(WHITEPAPER_CHART_SEQUENCE)} 张审计后分析图，每张图均配有证据边界说明。", "", "## 颜色图例", "", "- 🟥 优先改进", "- 🟧 需要关注", "- 🟩 表现较好", "- 🟦 描述性/不可判优劣", "", "红橙绿按同一张图中的相对分位识别改进优先级，不是业务目标、显著性或因果效应。", "", "## 图表目录", ""]
    for i, spec in enumerate(WHITEPAPER_CHART_SEQUENCE, start=1):
        md.append(f"{i}. **{spec['caption']}**：{spec['note']}")
    md += ["", "## 行动", "", "1. 补齐下订、承诺交付和实际交付时间戳。", "2. 运行随机化跟进方式试点。", "3. 建立渠道级花费与触点路径。", ""]
    md_path = REPORTS_DIR / "W5_white_paper.md"; md_path.write_text("\n".join(md), encoding="utf-8")
    return docx_path, md_path


def generate_notebook() -> Path:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {"display_name": "G9 Analysis", "language": "python", "name": "g9-analysis"}
    notebook["cells"] = [
        nbf.v4.new_markdown_cell("# G9 因果归因重新分析\n\n## tl;dr\n\n本 Notebook 从不可修改的原始 Excel 重建清洗层与因果结果。结论只以执行输出为准。"),
        nbf.v4.new_markdown_cell("## Context & Methods\n\n### Key Assumptions\n\n- 下订时间戳缺失，因此跟进处理先于下订是不可验证假设。\n- PSM 只使用基线协变量，并以匹配后 SMD 判断平衡。\n- 交付记录关键字段冲突订单不进入主要估计。\n- RDD、多触点 Shapley 和渠道 ROI 在当前数据下不具备识别条件。"),
        nbf.v4.new_code_cell("from pathlib import Path\nimport json, sys\nROOT = Path.cwd()\nif not (ROOT / 'src').exists():\n    ROOT = ROOT.parent\nsys.path.insert(0, str(ROOT / 'src'))\nfrom g9_pipeline import build_clean_data, run_analysis\nbundle = build_clean_data(save=False)\nanalysis, charts = run_analysis(bundle, publish=False)\nprint('analysis generated:', analysis['generated_at'])"),
        nbf.v4.new_markdown_cell("## Data\n\n确认分析粒度、重复订单和时序异常。"),
        nbf.v4.new_code_cell("import pandas as pd\npd.DataFrame({\n    '表': ['线索级', '订单级', '跟进事件'],\n    '行数': [len(bundle.leads), len(bundle.orders), len(bundle.followups)],\n    '粒度': ['线索ID唯一', '订单ID唯一', '跟进ID事件']\n})"),
        nbf.v4.new_code_cell("pd.Series(bundle.audit['temporal_issues'], name='数量').to_frame()"),
        nbf.v4.new_markdown_cell("## Results\n\n### 跟进方式 PSM 与 AIPW"),
        nbf.v4.new_code_cell("pd.DataFrame([analysis['psm']['psm_att'], analysis['psm']['aipw_att']], index=['PSM ATT','AIPW ATT'])[['estimate','ci95','p_value','sample_size','balance_status','evidence_level']]"),
        nbf.v4.new_code_cell("charts['balance'].sort_values('匹配后SMD', key=lambda s: s.abs(), ascending=False).head(15)"),
        nbf.v4.new_markdown_cell("### 交付延迟与结果"),
        nbf.v4.new_code_cell("pd.DataFrame(analysis['delivery']).T[['estimate','ci95','p_value','sample_size','method','evidence_level']]"),
        nbf.v4.new_markdown_cell("### 渠道描述与标准化关联"),
        nbf.v4.new_code_cell("pd.DataFrame(analysis['channel']['descriptive'])"),
        nbf.v4.new_code_cell("pd.DataFrame(analysis['channel']['standardized'])"),
        nbf.v4.new_markdown_cell("## Takeaways\n\n- 匹配平衡通过，但面谈 ATT 的 95% 置信区间跨零。\n- 延迟交付对评分的调整后差异跨零。\n- 当前数据不能支持 RDD、多触点 Shapley 或渠道 ROI。\n- 所有结果应连同假设与证据等级一起使用。"),
    ]
    path = REPORTS_DIR / "W2_causal_attribution.ipynb"
    nbf.write(notebook, path)
    return path


def _pdf_styles():
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    try:
        pdfmetrics.registerFont(TTFont("MSYH", str(font_path), subfontIndex=0))
        font_name = "MSYH"
    except Exception:
        font_name = "Helvetica"
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("G9Title", parent=base["Title"], fontName=font_name, fontSize=24, leading=31, textColor=HexColor("#172033"), spaceAfter=18),
        "h1": ParagraphStyle("G9H1", parent=base["Heading1"], fontName=font_name, fontSize=16, leading=22, textColor=HexColor("#2E74B5"), spaceBefore=14, spaceAfter=8),
        "body": ParagraphStyle("G9Body", parent=base["BodyText"], fontName=font_name, fontSize=10.5, leading=17, textColor=HexColor("#172033"), spaceAfter=8),
        "bullet": ParagraphStyle("G9Bullet", parent=base["BodyText"], fontName=font_name, fontSize=10.5, leading=17, leftIndent=16, firstLineIndent=-8, spaceAfter=6),
        "caption": ParagraphStyle("G9Caption", parent=base["BodyText"], fontName=font_name, fontSize=8.5, leading=12, textColor=HexColor("#64748B"), alignment=1, spaceAfter=10),
    }
    return font_name, styles


def _pdf_page(canvas, doc):
    canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColorRGB(0.39, 0.45, 0.55)
    canvas.drawRightString(doc.pagesize[0] - 54, 28, f"Page {doc.page}"); canvas.restoreState()


def generate_pdf_reports(analysis: dict[str, Any], audit: dict[str, Any], images: dict[str, Path], strategy: pd.DataFrame) -> tuple[Path, Path]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    font_name, styles = _pdf_styles()
    psm = analysis["psm"]["psm_att"]; aipw = analysis["psm"]["aipw_att"]
    score = analysis["delivery"]["delivery_score_adjusted_association"]

    def image_block(key: str, caption: str):
        return [RLImage(str(images[key]), width=6.15 * inch, height=3.55 * inch), Paragraph(caption, styles["caption"])]

    def compact_image_block(key: str, caption: str, note: str):
        return KeepTogether([
            Paragraph(note, styles["body"]),
            RLImage(str(images[key]), width=5.55 * inch, height=3.05 * inch),
            Paragraph(caption, styles["caption"]),
        ])

    w2_path = REPORTS_DIR / "W2_causal_attribution_report.pdf"
    w2 = SimpleDocTemplate(str(w2_path), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=46, title="G9 因果归因与证据审计")
    story = [Paragraph("G9 因果归因与证据审计", styles["title"]), Paragraph("Executive Summary", styles["h1"])]
    bullets = [
        f"• 匹配后平衡通过，但面谈 ATT 为 {_pp(psm['estimate'])}，95% CI {_ci_pp(psm['ci95'])}，未发现可靠增益。",
        f"• AIPW 为 {_pp(aipw['estimate'])}，同样跨零。",
        f"• 延迟交付与评分的调整后差异为 {score['estimate']:+.3f} 分，置信区间跨零。",
        "• 数据不支持 RDD、多触点 Shapley 或渠道 ROI。",
    ]
    story += [Paragraph(item, styles["bullet"]) for item in bullets]
    story += [Paragraph("数据质量决定可用样本", styles["h1"]), Paragraph(f"5,000 条交付记录仅对应 {audit['row_counts']['unique_orders']:,} 个唯一订单；{audit['critical_conflict_orders']:,} 个订单存在关键字段冲突。主要交付分析只使用 {audit['usable_orders']:,} 个无关键冲突订单。", styles["body"])]
    story += image_block("propensity", "图 1. 倾向得分共同支持") + image_block("balance", "图 2. 匹配前后协变量平衡")
    story += [PageBreak(), Paragraph("跟进方式没有可靠的正向增益证据", styles["h1"])] + image_block("effects", "图 3. PSM 与 AIPW 效应估计") + image_block("sensitivity", "图 4. 隐藏偏差敏感性")
    data = [["分析", "估计", "95% CI", "证据等级"], ["PSM ATT", _pp(psm["estimate"]), _ci_pp(psm["ci95"]), psm["evidence_level"]], ["AIPW ATT", _pp(aipw["estimate"]), _ci_pp(aipw["ci95"]), aipw["evidence_level"]]]
    table = Table(data, colWidths=[1.2*inch,1.35*inch,2.2*inch,1.55*inch], repeatRows=1)
    table.setStyle(TableStyle([("FONTNAME",(0,0),(-1,-1),font_name),("FONTSIZE",(0,0),(-1,-1),8.5),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F2F4F7")),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CBD5E1")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)])); story += [table]
    story += [PageBreak(), Paragraph("交付延迟只能报告调整后关联", styles["h1"]), Paragraph("评分结果跨零，不能支持显著下降。投诉结果即使通过 FDR，也只是调整后关联，不能替代延迟机制和完整时间戳。", styles["body"])] + image_block("delivery", "图 5. 延迟交付调整后关联")
    story += [Paragraph("RDD 可行性审计", styles["h1"]), Paragraph("没有连续分配变量和事先确定阈值。交付里程中位数不是延迟交付规则，因此停止生成 McCrary、带宽和安慰剂 RDD 结论。", styles["body"])]
    story += [Paragraph("渠道结果是关联性比较", styles["h1"]), Paragraph("每条线索只有一个渠道；没有多触点路径和渠道级花费。每百线索订单数不是 ROI。", styles["body"])] + image_block("channel", "图 6. 渠道转化率及 95% CI") + image_block("channel_standardized", "图 7. 标准化边际转化率")
    story += [Paragraph("Recommended Next Steps", styles["h1"])] + [Paragraph(item, styles["bullet"]) for item in ["• 补采下订、承诺交付和实际交付时间戳。", "• 运行跟进方式随机化试点。", "• 建立渠道级花费和多触点路径，并把证据等级、置信区间与看板建议同步。"]]
    w2.build(story, onFirstPage=_pdf_page, onLaterPages=_pdf_page)

    w5_path = REPORTS_DIR / "W5_sales_operations_white_paper.pdf"
    w5 = SimpleDocTemplate(str(w5_path), pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=46, title="G9 销售运营证据白皮书")
    model = analysis["model"]["metrics"]
    white = [Paragraph("G9 销售运营证据白皮书", styles["title"]), Paragraph("Executive Summary", styles["h1"])]
    for item in [f"• 面谈 ATT 为 {_pp(psm['estimate'])}，不支持确定性扩张。", f"• 时间外 ROC AUC 为 {model['roc_auc']:.3f}，公开看板关闭逐客户预测。", "• 交付表关键冲突严重，延迟指标只使用无冲突订单。", "• 预算 ROI 改为机会优先级，所有建议需通过试验验证。"]:
        white.append(Paragraph(item, styles["bullet"]))
    color_legend = (
        f'<font color="{IMPROVE_RED}"><b>■ 优先改进</b></font>　'
        f'<font color="{WATCH_AMBER}"><b>■ 需要关注</b></font>　'
        f'<font color="{GOOD_GREEN}"><b>■ 表现较好</b></font>　'
        f'<font color="{NEUTRAL_BLUE}"><b>■ 描述性</b></font>'
    )
    white += [Paragraph("如何阅读这 40 张图", styles["h1"]), Paragraph("图表按描述性运营、因果诊断、调整后关联、预测解释和机会排序分层。图旁说明明确限制其解释边界，避免把相关性包装为因果结论。", styles["body"]), Paragraph(color_legend, styles["body"]), Paragraph("红橙绿按同图相对分位识别改进优先级，不代表业务目标、显著性或因果效应；蓝灰图只作描述。", styles["body"]), PageBreak()]
    current_section = None
    for figure_no, spec in enumerate(WHITEPAPER_CHART_SEQUENCE, start=1):
        if spec["section"] != current_section:
            current_section = spec["section"]
            white.append(Paragraph(current_section, styles["h1"]))
        white.append(compact_image_block(spec["key"], f"图 {figure_no}. {spec['caption']}", spec["note"]))
    white += [Paragraph("90 天实施路径", styles["h1"])] + [Paragraph(item, styles["bullet"]) for item in ["• 0-30 天：锁定唯一键、时间戳和冲突修复责任。", "• 31-60 天：开展跟进随机化试点并建立渠道花费明细。", "• 61-90 天：将实验结果、证据等级和数据哈希接入经营复盘。"]]
    w5.build(white, onFirstPage=_pdf_page, onLaterPages=_pdf_page)
    return w2_path, w5_path


def write_supporting_reports(analysis: dict[str, Any], strategy: pd.DataFrame) -> None:
    model = analysis["model"]["metrics"]
    w3 = ["# W3 时间外预测验证", "", f"- 时间外 ROC AUC：{model['roc_auc']:.3f}", f"- PR AUC：{model['pr_auc']:.3f}", f"- Brier Score：{model['brier_score']:.3f}", "- 仅使用线索创建时可得字段。", "- 原伪造生存时间分析已删除。", ""]
    (REPORTS_DIR / "W3_model_validation.md").write_text("\n".join(w3), encoding="utf-8")
    columns = ["城市", "渠道", "线索数", "订单数", "转化率", "跟进覆盖率", "优先级分", "建议"]
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    table_rows = []
    for _, row in strategy.head(15).iterrows():
        values = [row[c] for c in columns]
        values[4] = f"{float(values[4]):.1%}"; values[5] = f"{float(values[5]):.1%}"; values[6] = f"{float(values[6]):.1f}"
        table_rows.append("| " + " | ".join(str(v) for v in values) + " |")
    w4 = ["# W4 运营机会排序", "", "渠道级花费不可用，因此不计算 ROI/CPO。排序仅用于确定需要进一步诊断或试验的城市-渠道组合。", "", header, divider, *table_rows, ""]
    (REPORTS_DIR / "W4_strategy_report.md").write_text("\n".join(w4), encoding="utf-8")


def generate_all_reports(bundle: CleanBundle, analysis: dict[str, Any], charts: dict[str, pd.DataFrame]) -> dict[str, Path]:
    images = build_charts(charts, bundle, analysis)
    strategy = charts["strategy"]
    w2_docx = generate_w2_docx(analysis, bundle.audit, images)
    w5_docx, w5_md = generate_whitepaper(analysis, bundle.audit, images, strategy)
    w2_pdf, w5_pdf = generate_pdf_reports(analysis, bundle.audit, images, strategy)
    notebook = generate_notebook()
    write_supporting_reports(analysis, strategy)
    return {"w2_docx": w2_docx, "w2_pdf": w2_pdf, "w5_docx": w5_docx, "w5_pdf": w5_pdf, "w5_md": w5_md, "notebook": notebook, **images}
