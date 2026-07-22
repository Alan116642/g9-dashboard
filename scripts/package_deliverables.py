"""Build a local-only W1-W5 delivery package from audited artifacts."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from visual_catalog import WHITEPAPER_CHAPTER_STRUCTURE, WHITEPAPER_TASK_CHART_KEYS

OUT = (ROOT / "deliverables").resolve()
assert OUT.parent == ROOT.resolve(), f"Unexpected delivery path: {OUT}"


def copy_file(source: str | Path, destination: Path, rename: str | None = None) -> Path:
    source_path = (ROOT / source).resolve() if not Path(source).is_absolute() else Path(source)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (rename or source_path.name)
    shutil.copy2(source_path, target)
    return target


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def safe_name(text: str) -> str:
    for char in '<>:"/\\|?*':
        text = text.replace(char, "_")
    return text.strip().replace("  ", " ")


def copy_chart_set(keys: list[str], destination: Path, chart_map: dict) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for index, key in enumerate(keys, start=1):
        item = chart_map[key]
        source = ROOT / item["path"]
        copy_file(source, destination, f"{index:02d}_{source.name}")


if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

analysis = json.loads((ROOT / "data" / "processed" / "analysis_results.json").read_text(encoding="utf-8"))
audit = json.loads((ROOT / "data" / "processed" / "data_quality_audit.json").read_text(encoding="utf-8"))
chart_map = json.loads((ROOT / "reports" / "chart_map.json").read_text(encoding="utf-8"))

w1 = OUT / "W1_数据清洗与数据仓库建设"
w2 = OUT / "W2_因果推断与归因分析"
w3 = OUT / "W3_预测建模与智能预警"
w4 = OUT / "W4_策略仿真与优化"
w5 = OUT / "W5_决策看板与落地汇报"

# W1
for source in [
    "data/wide_table.csv",
    "data/processed/wide_table.parquet",
    "data/processed/lead_level.csv",
    "data/processed/lead_level.parquet",
    "data/processed/order_level.csv",
    "data/processed/order_level.parquet",
    "data/processed/followup_events.csv",
    "data/processed/followup_events.parquet",
]:
    copy_file(source, w1 / "数据")
for source in [
    "reports/W1_data_quality_report.md",
    "reports/W1_数据清洗与数仓建设报告.docx",
    "data/processed/data_quality_audit.json",
]:
    copy_file(source, w1 / "报告")
for source in ["src/w1_cleaning.py", "src/g9_pipeline.py", "src/config.py"]:
    copy_file(source, w1 / "代码")
copy_chart_set(WHITEPAPER_TASK_CHART_KEYS["W1 数据清洗与数据仓库建设"], w1 / "图表", chart_map)

# W2
for source in [
    "reports/W2_causal_attribution.ipynb",
    "reports/W2_causal_attribution_executed.ipynb",
    "reports/W2_causal_attribution_report.pdf",
    "reports/W2_因果推断与归因分析报告.docx",
    "data/processed/analysis_results.json",
]:
    copy_file(source, w2 / ("Notebook" if str(source).endswith(".ipynb") else "报告"))
for source in ["src/w2_causal.py", "src/g9_pipeline.py", "src/visual_catalog.py"]:
    copy_file(source, w2 / "代码")
copy_chart_set(WHITEPAPER_TASK_CHART_KEYS["W2 因果推断与归因分析"], w2 / "图表", chart_map)

# W3
for source in ["models/conversion_model.pkl"]:
    copy_file(source, w3 / "模型")
for source in ["reports/W3_model_validation.md", "reports/W3_预测建模与智能预警报告.docx"]:
    copy_file(source, w3 / "报告")
for source in ["src/w3_modeling.py", "src/g9_pipeline.py"]:
    copy_file(source, w3 / "代码")
copy_chart_set(WHITEPAPER_TASK_CHART_KEYS["W3 预测建模与智能预警"], w3 / "图表", chart_map)

# W4
for source in [
    "reports/W4_strategy_comparison.csv",
    "reports/W4_strategy_report.md",
    "reports/W4_策略仿真与优化报告.docx",
    "reports/W4_策略方案对比表.xlsx",
]:
    copy_file(source, w4 / ("方案表" if str(source).endswith((".csv", ".xlsx")) else "报告"))
for source in ["src/w4_optimization.py", "src/g9_pipeline.py", "scripts/build_w4_excel.mjs"]:
    copy_file(source, w4 / "代码")
copy_chart_set(WHITEPAPER_TASK_CHART_KEYS["W4 策略仿真与优化"], w4 / "图表", chart_map)

# W5
copy_file("reports/G9_销售运营优化白皮书_证据审计版.docx", w5 / "白皮书", "G9_销售运营优化白皮书.docx")
copy_file("reports/W5_sales_operations_white_paper.pdf", w5 / "白皮书", "G9_销售运营优化白皮书.pdf")
copy_file("reports/W5_white_paper.md", w5 / "白皮书", "G9_销售运营优化白皮书.md")
copy_file("reports/W5_evidence_decision_deck.pptx", w5 / "汇报PPT", "G9_董事会汇报_证据审计版.pptx")
for source in ["dashboard/app.py", "requirements.txt", ".streamlit/config.toml"]:
    copy_file(source, w5 / "看板代码")
for source in [
    "data_demo/dashboard_lead_cube.csv",
    "data_demo/dashboard_order_cube.csv",
    "data_demo/analysis_results.json",
    "data_demo/dashboard_metadata.json",
    "data_demo/W4_strategy_comparison.csv",
]:
    copy_file(source, w5 / "看板公开数据")
copy_chart_set(WHITEPAPER_TASK_CHART_KEYS["W5 决策看板与落地汇报"], w5 / "看板图表", chart_map)

# A second copy of all 54 white-paper figures, organized by the requested chapter structure.
whitepaper_figures = w5 / "白皮书" / "白皮书图表_54张"
figure_index = 1
for chapter_index, chapter in enumerate(WHITEPAPER_CHAPTER_STRUCTURE, start=1):
    chapter_dir = whitepaper_figures / f"{chapter_index:02d}_{safe_name(chapter['chapter'])}"
    for section in chapter["sections"]:
        for key in section["keys"]:
            item = chart_map[key]
            source = ROOT / item["path"]
            copy_file(source, chapter_dir, f"{figure_index:02d}_{source.name}")
            figure_index += 1
assert figure_index == 55, f"Expected 54 white-paper figures, got {figure_index - 1}"

write_text(
    w5 / "看板本地启动说明.md",
    r"""
# 看板本地启动

在项目根目录执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:APP_PASSWORD="请使用你在 Streamlit Secrets 中配置的密码"
python -m streamlit run dashboard/app.py
```

公开部署只读取 `看板公开数据` 中的脱敏聚合文件；不要上传 W1 明细、原始 Excel 或 W3 模型。
""",
)

psm = analysis["psm"]["psm_att"]
model = analysis["model"]["metrics"]
acceptance = f"""
# G9 五周交付物总验收清单

生成时间：{analysis['generated_at']}  
数据截止：线索 {psm['data_as_of']}；交付 {analysis['delivery']['delivery_score_adjusted_association']['data_as_of']}  
原始数据 SHA-256：`{analysis['source_sha256']}`

## 总体结论

五周交付文件已按 W1–W5 分目录整理，并补齐 CSV/Parquet、可执行 Notebook、模型、Excel、看板、白皮书、PDF 与 PPT。原任务中缺乏识别条件的部分没有伪造结果，而是保留为可行性审计或合规替代，因此整体状态为 **可交付，但必须附带证据边界**。

| 周次 | 原要求 | 验收状态 | 主要交付与边界 |
|---|---|---|---|
| W1 | 宽表、缺失/异常处理、数据质量报告 | 已完成 | 三张主表、宽表、CSV/Parquet、审计 JSON、报告；{audit['critical_conflict_orders']:,} 个关键冲突订单不进入主要交付估计。 |
| W2 | PSM、RDD、Shapley、Notebook/PDF | 条件完成 | PSM 平衡通过，但 ATT={psm['estimate']:.4f}，95%CI [{psm['ci95'][0]:.4f}, {psm['ci95'][1]:.4f}]，未发现可靠增益；RDD 因无合法断点变量被阻止；单触点数据不计算真实 Shapley 或渠道 ROI。 |
| W3 | 转化预测、生存预警、SHAP/重要性、模型 | 基线完成 | 时间顺序验证 AUC={model['roc_auc']:.3f}，仅作低辨识度基线；因无有效事件时间，不输出 Cox/随机生存森林，改为聚合风险分层。 |
| W4 | 预算、定价、排班优化、Excel | 合规替代 | 已交付机会优先级、方法可行性审计和 Excel；缺少渠道成本、竞品价格弹性和排班约束，因此不输出伪 ROI、伪博弈或伪整数规划解。 |
| W5 | 六页看板、白皮书、PDF、PPT | 已完成 | 白皮书按参考结构重构并包含 54 张中文图；线上仅用脱敏聚合数据，逐客户预测和明细展示关闭。 |

## 关键数据质量事实

- 原始线索 {audit['row_counts']['raw_leads']:,} 条、跟进 {audit['row_counts']['raw_followups']:,} 条、交付原始行 {audit['row_counts']['raw_delivery_rows']:,} 条。
- 唯一订单 {audit['row_counts']['unique_orders']:,} 个，其中可用于主要交付分析 {audit['usable_orders']:,} 个。
- 入职前跟进 {audit['temporal_issues']['followups_before_hire']:,} 条、交付后跟进 {audit['temporal_issues']['followups_after_delivery']:,} 条、首次日多方式模糊线索 {audit['temporal_issues']['leads_with_ambiguous_first_day_method']:,} 条，均按审计规则处理。
- 原始 Excel 在流水线重算前后哈希一致，没有被修改。

## 分享限制

- `deliverables` 是本地完整交付包，包含明细和模型，不应整体上传 GitHub。
- GitHub/Streamlit 只能使用 W5 `看板公开数据` 的脱敏聚合文件。
- 密码只放 Streamlit Secrets 或本地环境变量，不写入代码、README、白皮书或公开数据。
"""
write_text(OUT / "交付物总验收清单.md", acceptance)

index_lines = [
    "# G9 智能销售运营决策交付索引",
    "",
    "本目录按五周任务分块；详细完成度和方法边界见 `交付物总验收清单.md`。",
    "",
    "- `W1_数据清洗与数据仓库建设`：数据、Parquet、质量报告、代码、图表",
    "- `W2_因果推断与归因分析`：原始/已执行 Notebook、DOCX/PDF、统一结果 JSON、代码、图表",
    "- `W3_预测建模与智能预警`：模型、验证报告、代码、图表",
    "- `W4_策略仿真与优化`：Excel/CSV、策略报告、代码、图表",
    "- `W5_决策看板与落地汇报`：看板、公开数据、54 图白皮书、PDF、PPT",
]
write_text(OUT / "README.md", "\n".join(index_lines))

manifest_rows = []
for path in sorted(p for p in OUT.rglob("*") if p.is_file()):
    manifest_rows.append(
        {
            "path": path.relative_to(OUT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    )
(OUT / "交付物文件清单.json").write_text(
    json.dumps({"file_count": len(manifest_rows), "files": manifest_rows}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(f"Packaged {len(manifest_rows)} files into {OUT}")
