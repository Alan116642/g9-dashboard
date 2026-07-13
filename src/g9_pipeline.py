"""G9 source-backed analytics pipeline.

The workbook is treated as immutable. All outputs are derived into ``data/``
(private, git-ignored), ``data_demo/`` (public aggregate only), and ``reports/``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pickle
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import binom
from sklearn.compose import ColumnTransformer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = ROOT / "data" / "processed"
PUBLIC_DIR = ROOT / "data_demo"
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"
CHART_DIR = REPORTS_DIR / "W2_charts"
SEED = 42
ALPHA = 0.05
BOOTSTRAPS = 1000


def ensure_dirs() -> None:
    for path in (PRIVATE_DIR, PUBLIC_DIR, REPORTS_DIR, MODELS_DIR, CHART_DIR):
        path.mkdir(parents=True, exist_ok=True)


def workbook_path() -> Path:
    matches = sorted(ROOT.glob("*.xlsx"))
    if not matches:
        raise FileNotFoundError("No source .xlsx workbook found in project root")
    if len(matches) > 1:
        exact = [p for p in matches if "销售运营数据" in p.name]
        if len(exact) == 1:
            return exact[0]
        raise RuntimeError(f"Expected one source workbook, found: {[p.name for p in matches]}")
    return matches[0]


def source_sha256() -> str:
    h = hashlib.sha256()
    with workbook_path().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def mode_value(series: pd.Series) -> Any:
    clean = series.dropna()
    if clean.empty:
        return np.nan
    modes = clean.mode(dropna=True)
    return modes.sort_values(key=lambda s: s.astype(str)).iloc[0]


def load_raw_workbook() -> dict[str, pd.DataFrame]:
    path = workbook_path()
    excel = pd.ExcelFile(path)
    required = ["销售线索", "跟进日志", "交付记录", "售后工单", "销售员信息", "门店成本"]
    missing = [sheet for sheet in required if sheet not in excel.sheet_names]
    if missing:
        raise ValueError(f"Workbook missing required sheets: {missing}")
    return {sheet: pd.read_excel(path, sheet_name=sheet) for sheet in required}


ORDER_FIELDS = ["线索ID", "交付日期", "车型", "配置", "颜色", "交付里程", "是否延迟交付", "交付评分"]
CRITICAL_ORDER_FIELDS = ["交付日期", "配置", "交付里程", "是否延迟交付", "交付评分"]


def reconcile_orders(delivery: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate order rows deterministically and retain conflict flags."""
    work = delivery.copy()
    work["交付日期"] = pd.to_datetime(work["交付日期"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for order_id, group in work.groupby("订单ID", sort=True, dropna=False):
        row: dict[str, Any] = {"订单ID": order_id, "原始记录数": int(len(group))}
        for field in ORDER_FIELDS:
            values = group[field].dropna().unique()
            row[f"{field}_冲突"] = bool(len(values) > 1)
            if field == "交付日期":
                row[field] = group[field].min()
            elif field == "交付里程":
                row[field] = float(group[field].median()) if group[field].notna().any() else np.nan
            elif field == "交付评分":
                row[field] = float(group[field].mean()) if group[field].notna().any() else np.nan
            else:
                row[field] = mode_value(group[field])
        row["关键冲突"] = any(row[f"{field}_冲突"] for field in CRITICAL_ORDER_FIELDS)
        rows.append(row)
    result = pd.DataFrame(rows)
    result["交付月份"] = result["交付日期"].dt.to_period("M").astype(str)
    return result


def _first_followup_exposure(valid_followups: pd.DataFrame) -> pd.DataFrame:
    if valid_followups.empty:
        return pd.DataFrame(columns=["线索ID", "首次有效跟进日期", "首次跟进方式", "首次同日方式数", "面谈处理", "处理模糊"])
    first_date = valid_followups.groupby("线索ID")["跟进日期"].min().rename("首次有效跟进日期")
    first_rows = valid_followups.merge(first_date, left_on=["线索ID", "跟进日期"], right_on=["线索ID", "首次有效跟进日期"])
    records = []
    for lead_id, group in first_rows.groupby("线索ID", sort=False):
        methods = sorted(group["跟进方式"].dropna().astype(str).unique())
        ambiguous = len(methods) != 1
        records.append({
            "线索ID": lead_id,
            "首次有效跟进日期": group["首次有效跟进日期"].iloc[0],
            "首次跟进方式": "+".join(methods),
            "首次同日方式数": len(methods),
            "面谈处理": int(methods == ["面谈"]) if not ambiguous else np.nan,
            "处理模糊": ambiguous,
        })
    return pd.DataFrame(records)


@dataclass
class CleanBundle:
    leads: pd.DataFrame
    orders: pd.DataFrame
    followups: pd.DataFrame
    audit: dict[str, Any]


def build_clean_data(save: bool = True) -> CleanBundle:
    ensure_dirs()
    raw = load_raw_workbook()
    leads = raw["销售线索"].copy()
    followups = raw["跟进日志"].copy()
    sales = raw["销售员信息"].copy()
    aftersales = raw["售后工单"].copy()
    orders = reconcile_orders(raw["交付记录"])

    leads["日期"] = pd.to_datetime(leads["日期"], errors="coerce")
    leads["月份"] = leads["日期"].dt.to_period("M").astype(str)
    leads["年龄段"] = pd.cut(
        leads["客户年龄"], bins=[17, 24, 29, 34, 39, 49, 120],
        labels=["18-24", "25-29", "30-34", "35-39", "40-49", "50+"], right=True,
    ).astype(str)
    followups["跟进日期"] = pd.to_datetime(followups["跟进日期"], errors="coerce")
    sales["入职日期"] = pd.to_datetime(sales["入职日期"], errors="coerce")
    aftersales["工单日期"] = pd.to_datetime(aftersales["工单日期"], errors="coerce")

    if leads["线索ID"].duplicated().any():
        raise ValueError("销售线索 sheet is not unique at 线索ID grain")
    if sales["销售员ID"].duplicated().any():
        raise ValueError("销售员信息 sheet is not unique at 销售员ID grain")

    earliest_delivery = orders.groupby("线索ID")["交付日期"].min().rename("最早交付日期")
    followups = followups.merge(sales[["销售员ID", "入职日期", "职级", "绩效评级"]], on="销售员ID", how="left", validate="many_to_one")
    followups = followups.merge(earliest_delivery, on="线索ID", how="left", validate="many_to_one")
    followups["入职后跟进"] = followups["入职日期"].notna() & (followups["跟进日期"] >= followups["入职日期"])
    followups["交付前跟进"] = followups["最早交付日期"].isna() | (followups["跟进日期"] <= followups["最早交付日期"])
    followups["有效跟进"] = followups["入职后跟进"] & followups["交付前跟进"] & followups["线索ID"].isin(leads["线索ID"])
    valid_followups = followups.loc[followups["有效跟进"]].copy()

    exposure = _first_followup_exposure(valid_followups)
    follow_stats = valid_followups.groupby("线索ID").agg(
        有效跟进次数=("跟进ID", "nunique"),
        有效沟通总时长=("沟通时长(分钟)", "sum"),
        平均沟通时长=("沟通时长(分钟)", "mean"),
        面谈次数=("跟进方式", lambda s: int((s == "面谈").sum())),
        主要销售员ID=("销售员ID", mode_value),
    ).reset_index()
    lead_level = leads.merge(follow_stats, on="线索ID", how="left", validate="one_to_one").merge(exposure, on="线索ID", how="left", validate="one_to_one")
    for column in ["有效跟进次数", "有效沟通总时长", "面谈次数", "首次同日方式数"]:
        lead_level[column] = lead_level[column].fillna(0).astype(int)
    lead_level["有效跟进线索"] = (lead_level["有效跟进次数"] > 0).astype(int)
    lead_level["面谈占比"] = np.where(lead_level["有效跟进次数"] > 0, lead_level["面谈次数"] / lead_level["有效跟进次数"], np.nan)

    complaint = aftersales.groupby("订单ID").agg(
        投诉工单数=("工单ID", "nunique"),
        平均售后满意度=("满意度评分", "mean"),
        平均处理时长天=("处理时长(天)", "mean"),
        首次工单日期=("工单日期", "min"),
    ).reset_index()
    orders = orders.merge(complaint, on="订单ID", how="left", validate="one_to_one")
    orders["投诉工单数"] = orders["投诉工单数"].fillna(0).astype(int)
    orders["有投诉"] = (orders["投诉工单数"] > 0).astype(int)
    orders = orders.merge(leads[["线索ID", "城市", "渠道", "日期", "月份"]], on="线索ID", how="left", validate="many_to_one")
    orders["工单早于交付"] = orders["首次工单日期"].notna() & (orders["首次工单日期"] < orders["交付日期"])

    order_groups = raw["交付记录"].groupby("订单ID").size()
    conflict_counts = {field: int(orders[f"{field}_冲突"].sum()) for field in ORDER_FIELDS}
    audit = {
        "source": workbook_path().name,
        "source_sha256": source_sha256(),
        "generated_at": datetime.now().astimezone().isoformat(),
        "grain": {"lead_level": "one row per 线索ID", "order_level": "one row per 订单ID", "followup_events": "one row per 跟进ID"},
        "row_counts": {
            "raw_leads": len(leads), "raw_followups": len(followups), "raw_delivery_rows": len(raw["交付记录"]),
            "unique_orders": len(orders), "raw_aftersales": len(aftersales), "valid_followups": len(valid_followups),
        },
        "duplicates": {
            "duplicate_delivery_rows_beyond_unique_order": int(len(raw["交付记录"]) - raw["交付记录"]["订单ID"].nunique()),
            "orders_with_duplicate_rows": int((order_groups > 1).sum()),
            "max_rows_per_order": int(order_groups.max()),
        },
        "order_conflicts": conflict_counts,
        "critical_conflict_orders": int(orders["关键冲突"].sum()),
        "usable_orders": int((~orders["关键冲突"]).sum()),
        "temporal_issues": {
            "followups_before_hire": int((~followups["入职后跟进"]).sum()),
            "followups_after_delivery": int((~followups["交付前跟进"]).sum()),
            "leads_with_ambiguous_first_day_method": int(exposure["处理模糊"].sum()) if not exposure.empty else 0,
            "orders_with_ticket_before_delivery": int(orders["工单早于交付"].sum()),
        },
        "severity": "critical",
        "decision": "Conflicted orders are excluded from primary delivery-effect estimation; invalid follow-ups are excluded from treatment construction.",
    }

    if save:
        lead_level.to_csv(PRIVATE_DIR / "lead_level.csv", index=False, encoding="utf-8-sig")
        orders.to_csv(PRIVATE_DIR / "order_level.csv", index=False, encoding="utf-8-sig")
        followups.to_csv(PRIVATE_DIR / "followup_events.csv", index=False, encoding="utf-8-sig")
        write_json(PRIVATE_DIR / "data_quality_audit.json", audit)
        build_quality_markdown(audit)
    return CleanBundle(lead_level, orders, followups, audit)


def build_quality_markdown(audit: dict[str, Any]) -> None:
    rc, dup, temp = audit["row_counts"], audit["duplicates"], audit["temporal_issues"]
    conflicts = audit["order_conflicts"]
    lines = [
        "# W1 数据质量审计报告", "", f"数据源：`{audit['source']}`", f"生成时间：{audit['generated_at']}", "",
        "## 结论", "", "交付记录存在严重的订单粒度重复和字段冲突，不能直接按行用于交付效果分析。清洗层已保留冲突标记，并将关键冲突订单排除出主要估计。", "",
        "## 数据规模", "", f"- 线索：{rc['raw_leads']:,}", f"- 跟进：{rc['raw_followups']:,}（有效 {rc['valid_followups']:,}）",
        f"- 交付原始行：{rc['raw_delivery_rows']:,}；唯一订单：{rc['unique_orders']:,}", f"- 售后工单：{rc['raw_aftersales']:,}", "",
        "## 关键问题", "", f"- 重复交付行（超过唯一订单部分）：{dup['duplicate_delivery_rows_beyond_unique_order']:,}",
        f"- 存在重复记录的订单：{dup['orders_with_duplicate_rows']:,}；单订单最多 {dup['max_rows_per_order']} 行",
        f"- 关键字段冲突订单：{audit['critical_conflict_orders']:,}；可用于主要交付分析的订单：{audit['usable_orders']:,}",
    ]
    for field, count in conflicts.items():
        lines.append(f"- `{field}` 冲突订单：{count:,}")
    lines += ["", "## 时序问题", "", f"- 入职前跟进：{temp['followups_before_hire']:,}", f"- 交付后跟进：{temp['followups_after_delivery']:,}",
              f"- 首次有效跟进日存在多种方式的线索：{temp['leads_with_ambiguous_first_day_method']:,}", f"- 工单日期早于交付日期的订单：{temp['orders_with_ticket_before_delivery']:,}", "",
              "## 处理规则", "", "- 原始 Excel 保持不变。", "- 交付记录按订单 ID 聚合，所有冲突保留显式标记。", "- 主要交付分析只使用无关键冲突订单。",
              "- 跟进处理仅使用入职后且不晚于已知交付日的事件。", "- 同日多方式首次跟进不进入主要 PSM，只进入敏感性说明。", ""]
    (REPORTS_DIR / "W1_data_quality_report.md").write_text("\n".join(lines), encoding="utf-8")


def _base_design(df: pd.DataFrame, include_channel: bool = True) -> tuple[pd.DataFrame, list[str], list[str]]:
    numeric = ["客户年龄", "试驾时长"]
    categorical = ["客户性别", "城市", "月份"] + (["渠道"] if include_channel else [])
    work = df[numeric + categorical].copy()
    for col in numeric:
        work[col] = pd.to_numeric(work[col], errors="coerce").fillna(work[col].median())
    for col in categorical:
        work[col] = work[col].fillna("未知").astype(str)
    design = pd.get_dummies(work, columns=categorical, dtype=float)
    return design.astype(float), numeric, categorical


def _smd(frame: pd.DataFrame, treatment: pd.Series) -> pd.Series:
    t = frame.loc[treatment.astype(bool)]
    c = frame.loc[~treatment.astype(bool)]
    pooled = np.sqrt((t.var(ddof=1) + c.var(ddof=1)) / 2).replace(0, np.nan)
    return ((t.mean() - c.mean()) / pooled).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _greedy_exact_match(
    data: pd.DataFrame, logits: pd.Series, treatment: pd.Series, caliper: float,
) -> tuple[list[int], list[int]]:
    controls: dict[tuple[str, str], list[tuple[float, int]]] = {}
    for idx in data.index[~treatment.astype(bool)]:
        key = (str(data.at[idx, "城市"]), str(data.at[idx, "月份"]))
        controls.setdefault(key, []).append((float(logits.at[idx]), int(idx)))
    for key in controls:
        controls[key].sort()
    treated_order = sorted(data.index[treatment.astype(bool)], key=lambda i: float(logits.at[i]))
    matched_t, matched_c = [], []
    for idx in treated_order:
        key = (str(data.at[idx, "城市"]), str(data.at[idx, "月份"]))
        pool = controls.get(key, [])
        if not pool:
            continue
        target = float(logits.at[idx])
        position = bisect_left(pool, (target, -1))
        candidates = []
        if position < len(pool):
            candidates.append((abs(pool[position][0] - target), position))
        if position > 0:
            candidates.append((abs(pool[position - 1][0] - target), position - 1))
        distance, chosen = min(candidates)
        if distance <= caliper:
            _, control_idx = pool.pop(chosen)
            matched_t.append(int(idx))
            matched_c.append(control_idx)
    return matched_t, matched_c


def result_record(
    *, estimand: str, estimate: float | None, standard_error: float | None,
    ci95: Iterable[float | None], p_value: float | None, sample_size: int,
    method: str, balance_status: str, assumptions: list[str], evidence_level: str,
    data_as_of: str,
) -> dict[str, Any]:
    return {
        "estimand": estimand, "estimate": estimate, "standard_error": standard_error,
        "ci95": list(ci95), "p_value": p_value, "sample_size": int(sample_size),
        "method": method, "balance_status": balance_status, "assumptions": assumptions,
        "evidence_level": evidence_level, "data_as_of": data_as_of,
    }


def run_psm(leads: pd.DataFrame) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    unambiguous = leads["处理模糊"].notna() & leads["处理模糊"].eq(False)
    cohort = leads.loc[(leads["有效跟进线索"] == 1) & unambiguous & leads["面谈处理"].notna()].copy().reset_index(drop=True)
    treatment = cohort["面谈处理"].astype(int)
    outcome = cohort["是否下订"].astype(int)
    design, _, _ = _base_design(cohort)
    scaler = StandardScaler()
    design_scaled = scaler.fit_transform(design)
    propensity_model = LogisticRegression(max_iter=2000, class_weight=None, random_state=SEED)
    propensity_model.fit(design_scaled, treatment)
    propensity = pd.Series(propensity_model.predict_proba(design_scaled)[:, 1], index=cohort.index).clip(1e-6, 1 - 1e-6)
    logits = np.log(propensity / (1 - propensity))
    support_low = max(propensity[treatment == 1].min(), propensity[treatment == 0].min())
    support_high = min(propensity[treatment == 1].max(), propensity[treatment == 0].max())
    in_support = propensity.between(support_low, support_high)
    cohort_s = cohort.loc[in_support].copy()
    design_s = design.loc[in_support].copy()
    t_s = treatment.loc[in_support]
    y_s = outcome.loc[in_support]
    logit_s = logits.loc[in_support]
    caliper = 0.2 * float(logit_s.std(ddof=1))
    matched_t, matched_c = _greedy_exact_match(cohort_s, logit_s, t_s, caliper)
    if len(matched_t) < 30:
        raise RuntimeError(f"PSM produced only {len(matched_t)} matched pairs")
    pair_diff = y_s.loc[matched_t].to_numpy(dtype=float) - y_s.loc[matched_c].to_numpy(dtype=float)
    rng = np.random.default_rng(SEED)
    boot = np.array([pair_diff[rng.integers(0, len(pair_diff), len(pair_diff))].mean() for _ in range(BOOTSTRAPS)])
    att = float(pair_diff.mean())
    se = float(boot.std(ddof=1))
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
    p_value = float(stats.ttest_1samp(pair_diff, popmean=0).pvalue)
    before_smd = _smd(design_s, t_s)
    matched_design = pd.concat([design_s.loc[matched_t], design_s.loc[matched_c]], axis=0)
    matched_treatment = pd.Series([1] * len(matched_t) + [0] * len(matched_c), index=matched_design.index)
    after_smd = _smd(matched_design.reset_index(drop=True), matched_treatment.reset_index(drop=True))
    balance = pd.DataFrame({"协变量": design_s.columns, "匹配前SMD": before_smd.values, "匹配后SMD": after_smd.values})
    max_smd = float(balance["匹配后SMD"].abs().max())
    balance_status = "passed" if max_smd < 0.1 else "failed"

    # AIPW ATT robustness estimate using a treatment-aware outcome regression.
    outcome_design = np.column_stack([treatment.to_numpy(), design_scaled])
    outcome_model = LogisticRegression(max_iter=2000, random_state=SEED)
    outcome_model.fit(outcome_design, outcome)
    x0 = outcome_design.copy(); x0[:, 0] = 0
    m0 = outcome_model.predict_proba(x0)[:, 1]
    e = propensity.to_numpy()
    t = treatment.to_numpy(dtype=float); y = outcome.to_numpy(dtype=float)
    treated_share = t.mean()
    influence = (t * (y - m0) - (1 - t) * e / (1 - e) * (y - m0)) / treated_share
    aipw = float(influence.mean())
    aipw_se = float(influence.std(ddof=1) / math.sqrt(len(influence)))
    aipw_ci = [aipw - 1.96 * aipw_se, aipw + 1.96 * aipw_se]
    aipw_p = float(2 * stats.norm.sf(abs(aipw / aipw_se))) if aipw_se > 0 else None

    b = int(((y_s.loc[matched_t].to_numpy() == 1) & (y_s.loc[matched_c].to_numpy() == 0)).sum())
    c = int(((y_s.loc[matched_t].to_numpy() == 0) & (y_s.loc[matched_c].to_numpy() == 1)).sum())
    discordant = b + c
    favorable = max(b, c)
    sensitivity_rows = []
    for gamma in np.linspace(1, 3, 21):
        upper_probability = gamma / (1 + gamma)
        p_upper = min(1.0, 2 * float(binom.sf(favorable - 1, discordant, upper_probability))) if discordant else 1.0
        sensitivity_rows.append({"Gamma": float(gamma), "p值上界": p_upper})
    sensitivity = pd.DataFrame(sensitivity_rows)

    as_of = str(cohort["日期"].max().date())
    reliable = balance_status == "passed" and ci[0] > 0
    evidence = "conditional_causal_positive" if reliable else "conditional_causal_no_reliable_gain"
    assumptions = [
        "No unmeasured confounding after adjustment for observed baseline covariates.",
        "The first valid follow-up occurred before ordering; order timestamps are unavailable, so this cannot be verified.",
        "Treatment is the only method recorded on the first valid follow-up date; ambiguous same-day methods are excluded.",
        "Exact matching is enforced within city and lead month.",
    ]
    results = {
        "psm_att": result_record(
            estimand="ATT of first-day face-to-face follow-up on lead conversion",
            estimate=att, standard_error=se, ci95=ci, p_value=p_value, sample_size=2 * len(matched_t),
            method="1:1 nearest-neighbor PSM without replacement; 0.2 SD logit caliper; exact city and month; 1,000 paired bootstraps",
            balance_status=balance_status, assumptions=assumptions, evidence_level=evidence, data_as_of=as_of,
        ),
        "aipw_att": result_record(
            estimand="Doubly robust ATT robustness estimate",
            estimate=aipw, standard_error=aipw_se, ci95=aipw_ci, p_value=aipw_p, sample_size=len(cohort),
            method="AIPW ATT with logistic propensity and treatment-aware logistic outcome model",
            balance_status="not_applicable", assumptions=assumptions, evidence_level="robustness_check", data_as_of=as_of,
        ),
        "diagnostics": {
            "eligible_leads": len(cohort), "treated_leads": int(treatment.sum()), "control_leads": int((1 - treatment).sum()),
            "matched_pairs": len(matched_t), "common_support": [float(support_low), float(support_high)], "caliper": caliper,
            "max_abs_smd_after": max_smd, "discordant_pairs": discordant, "treated_favorable_pairs": b, "control_favorable_pairs": c,
        },
    }
    chart_data = {
        "propensity": pd.DataFrame({"倾向得分": propensity, "处理组": np.where(treatment == 1, "首次面谈", "其他方式")}),
        "balance": balance,
        "effects": pd.DataFrame([
            {"方法": "PSM ATT", "估计": att, "下限": ci[0], "上限": ci[1]},
            {"方法": "AIPW ATT", "估计": aipw, "下限": aipw_ci[0], "上限": aipw_ci[1]},
        ]),
        "sensitivity": sensitivity,
    }
    return results, chart_data


def _robust_ols(data: pd.DataFrame, outcome: str, treatment_col: str, controls: list[str]) -> tuple[float, float, list[float], float]:
    import statsmodels.api as sm
    design = pd.get_dummies(data[[treatment_col] + controls], columns=[c for c in controls if data[c].dtype == object], drop_first=True, dtype=float)
    design = design.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    x = sm.add_constant(design, has_constant="add")
    model = sm.OLS(pd.to_numeric(data[outcome], errors="coerce"), x).fit(cov_type="HC3")
    estimate = float(model.params[treatment_col]); se = float(model.bse[treatment_col]); p = float(model.pvalues[treatment_col])
    return estimate, se, [estimate - 1.96 * se, estimate + 1.96 * se], p


def run_delivery_analysis(orders: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    usable = orders.loc[(~orders["关键冲突"]) & orders["交付评分"].notna() & orders["是否延迟交付"].notna()].copy()
    usable["是否延迟交付"] = usable["是否延迟交付"].astype(int)
    controls = ["城市", "配置", "交付月份"]
    adjusted, se, ci, p = _robust_ols(usable, "交付评分", "是否延迟交付", controls)
    delayed = usable.loc[usable["是否延迟交付"] == 1, "交付评分"]
    ontime = usable.loc[usable["是否延迟交付"] == 0, "交付评分"]
    raw_diff = float(delayed.mean() - ontime.mean())
    raw_test = stats.ttest_ind(delayed, ontime, equal_var=False, nan_policy="omit")
    raw_se = float(math.sqrt(delayed.var(ddof=1) / len(delayed) + ontime.var(ddof=1) / len(ontime)))
    complaint_est, complaint_se, complaint_ci, complaint_p = _robust_ols(usable, "有投诉", "是否延迟交付", controls)
    as_of = str(usable["交付日期"].max().date()) if len(usable) else "unknown"
    assumptions = [
        "Only orders without conflicts in delivery date, configuration, mileage, delay flag, and score are included.",
        "City, configuration, and delivery month are adjusted; unmeasured delivery complexity may remain.",
        "Promised and actual delivery dates are unavailable, so delay severity and an assignment threshold cannot be reconstructed.",
    ]
    results = {
        "delivery_score_raw_difference": result_record(
            estimand="Mean delivery-score difference: delayed minus on-time",
            estimate=raw_diff, standard_error=raw_se, ci95=[raw_diff - 1.96 * raw_se, raw_diff + 1.96 * raw_se],
            p_value=float(raw_test.pvalue), sample_size=len(usable), method="Unadjusted Welch comparison",
            balance_status="not_applicable", assumptions=assumptions, evidence_level="descriptive_association", data_as_of=as_of,
        ),
        "delivery_score_adjusted_association": result_record(
            estimand="Adjusted delivery-score association with delay",
            estimate=adjusted, standard_error=se, ci95=ci, p_value=p, sample_size=len(usable),
            method="OLS with HC3 robust SE; controls: city, configuration, delivery month",
            balance_status="not_applicable", assumptions=assumptions, evidence_level="adjusted_association", data_as_of=as_of,
        ),
        "complaint_adjusted_association": result_record(
            estimand="Adjusted complaint-probability association with delay",
            estimate=complaint_est, standard_error=complaint_se, ci95=complaint_ci, p_value=complaint_p, sample_size=len(usable),
            method="Linear probability model with HC3 robust SE; controls: city, configuration, delivery month",
            balance_status="not_applicable", assumptions=assumptions, evidence_level="adjusted_association", data_as_of=as_of,
        ),
        "rdd_feasibility": result_record(
            estimand="RDD feasibility for delivery delay",
            estimate=None, standard_error=None, ci95=[None, None], p_value=None, sample_size=len(usable),
            method="Design audit: no continuous assignment variable with a known operational cutoff",
            balance_status="failed_design", assumptions=assumptions, evidence_level="not_identified", data_as_of=as_of,
        ),
    }
    from statsmodels.stats.multitest import multipletests
    q_values = multipletests([p, complaint_p], alpha=ALPHA, method="fdr_bh")[1]
    results["delivery_score_adjusted_association"]["q_value"] = float(q_values[0])
    results["complaint_adjusted_association"]["q_value"] = float(q_values[1])
    chart = pd.DataFrame([
        {"结果": "评分原始差异", "估计": raw_diff, "下限": raw_diff - 1.96 * raw_se, "上限": raw_diff + 1.96 * raw_se},
        {"结果": "评分调整后关联", "估计": adjusted, "下限": ci[0], "上限": ci[1]},
        {"结果": "投诉概率调整后关联", "估计": complaint_est, "下限": complaint_ci[0], "上限": complaint_ci[1]},
    ])
    return results, chart


def _wilson(success: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return np.nan, np.nan
    p = success / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return centre - margin, centre + margin


def run_channel_analysis(leads: pd.DataFrame) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    rows = []
    for channel, group in leads.groupby("渠道", sort=True):
        successes = int(group["是否下订"].sum()); total = len(group); low, high = _wilson(successes, total)
        rows.append({"渠道": channel, "线索数": total, "订单数": successes, "转化率": successes / total, "置信区间下限": low, "置信区间上限": high, "每百线索订单数": 100 * successes / total})
    descriptive = pd.DataFrame(rows)

    features = ["客户年龄", "客户性别", "试驾时长", "城市", "月份", "渠道"]
    numeric = ["客户年龄", "试驾时长"]
    categorical = ["客户性别", "城市", "月份", "渠道"]
    pre = ColumnTransformer([
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])
    standardization_model = Pipeline([("pre", pre), ("model", LogisticRegression(max_iter=2000, random_state=SEED))])
    standardization_model.fit(leads[features], leads["是否下订"].astype(int))
    standardized_rows = []
    for channel in sorted(leads["渠道"].dropna().unique()):
        counterfactual = leads[features].copy(); counterfactual["渠道"] = channel
        probability = standardization_model.predict_proba(counterfactual)[:, 1]
        standardized_rows.append({"渠道": channel, "标准化边际转化率": float(probability.mean())})
    standardized = pd.DataFrame(standardized_rows)
    as_of = str(leads["日期"].max().date())
    result = {
        "channel_attribution_scope": result_record(
            estimand="Adjusted marginal conversion probability by single acquisition channel",
            estimate=None, standard_error=None, ci95=[None, None], p_value=None, sample_size=len(leads),
            method="Descriptive Wilson intervals and logistic standardization; not multi-touch Shapley attribution",
            balance_status="not_applicable",
            assumptions=["Each lead has one acquisition channel.", "No channel-level spend or multi-touch path is available.", "Standardized differences are predictive/associational, not causal."],
            evidence_level="adjusted_association", data_as_of=as_of,
        ),
        "descriptive": descriptive.to_dict("records"),
        "standardized": standardized.to_dict("records"),
    }
    return result, {"descriptive": descriptive, "standardized": standardized}


def run_conversion_model(leads: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    features = ["日期", "客户年龄", "客户性别", "试驾时长", "城市", "渠道", "月份"]
    model_features = ["客户年龄", "客户性别", "试驾时长", "城市", "渠道", "月份"]
    data = leads[features + ["是否下订"]].sort_values("日期").reset_index(drop=True)
    split = int(len(data) * 0.8)
    train, test = data.iloc[:split], data.iloc[split:]
    numeric = ["客户年龄", "试驾时长"]
    categorical = ["客户性别", "城市", "渠道", "月份"]
    pre = ColumnTransformer([
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
    ])
    model = Pipeline([("pre", pre), ("model", LogisticRegression(max_iter=2000, random_state=SEED))])
    model.fit(train[model_features], train["是否下订"].astype(int))
    prob = model.predict_proba(test[model_features])[:, 1]
    metrics = {
        "roc_auc": float(roc_auc_score(test["是否下订"], prob)),
        "pr_auc": float(average_precision_score(test["是否下订"], prob)),
        "brier_score": float(brier_score_loss(test["是否下订"], prob)),
        "train_size": len(train), "test_size": len(test),
        "train_end": str(train["日期"].max().date()), "test_start": str(test["日期"].min().date()),
    }
    importance = permutation_importance(model, test[model_features], test["是否下订"].astype(int), n_repeats=10, random_state=SEED, scoring="roc_auc")
    importance_df = pd.DataFrame({"特征": model_features, "预测重要性": importance.importances_mean, "标准差": importance.importances_std}).sort_values("预测重要性", ascending=False)
    with (MODELS_DIR / "conversion_model.pkl").open("wb") as handle:
        pickle.dump({"pipeline": model, "features": model_features, "trained_at": datetime.now().isoformat(), "metrics": metrics}, handle)
    result = {
        "conversion_model": result_record(
            estimand="Out-of-time lead conversion prediction quality",
            estimate=metrics["roc_auc"], standard_error=None, ci95=[None, None], p_value=None, sample_size=len(test),
            method="Chronological 80/20 split; baseline-only logistic pipeline",
            balance_status="not_applicable",
            assumptions=["Only fields available at lead creation are used.", "Performance is predictive and does not imply causal feature effects."],
            evidence_level="predictive_validation", data_as_of=str(data["日期"].max().date()),
        ),
        "metrics": metrics,
        "feature_importance": importance_df.to_dict("records"),
        "survival_analysis_status": "removed: no valid event-time definition is available",
    }
    return result, importance_df


def build_strategy(leads: pd.DataFrame, model_importance: pd.DataFrame) -> pd.DataFrame:
    grouped = leads.groupby(["城市", "渠道"], as_index=False).agg(
        线索数=("线索ID", "nunique"), 订单数=("是否下订", "sum"), 有效跟进线索数=("有效跟进线索", "sum"), 有效跟进次数=("有效跟进次数", "sum"),
    )
    grouped["转化率"] = grouped["订单数"] / grouped["线索数"]
    grouped["跟进覆盖率"] = grouped["有效跟进线索数"] / grouped["线索数"]
    grouped["机会量"] = grouped["线索数"] * np.maximum(0, grouped["转化率"].median() - grouped["转化率"])
    grouped["优先级分"] = 100 * grouped["机会量"].rank(pct=True) * (0.5 + 0.5 * (1 - grouped["跟进覆盖率"]))
    grouped["建议"] = np.select(
        [grouped["优先级分"] >= grouped["优先级分"].quantile(0.75), grouped["跟进覆盖率"] < grouped["跟进覆盖率"].median()],
        ["优先诊断线索承接与跟进流程", "提升有效跟进覆盖"], default="保持监测并做小规模验证",
    )
    return grouped.sort_values("优先级分", ascending=False)


def _aggregate_cubes(leads: pd.DataFrame, orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lead_dims = ["月份", "城市", "渠道", "客户性别", "年龄段"]
    lead_cube = leads.groupby(lead_dims, observed=True, as_index=False).agg(
        线索数=("线索ID", "nunique"), 下订数=("是否下订", "sum"), 有效跟进线索数=("有效跟进线索", "sum"), 跟进次数合计=("有效跟进次数", "sum"),
    ).rename(columns={"客户性别": "性别"})
    usable_orders = orders.loc[~orders["关键冲突"]].copy()
    order_dims = ["交付月份", "城市", "渠道"]
    order_cube = usable_orders.groupby(order_dims, as_index=False).agg(
        有效订单数=("订单ID", "nunique"), 延迟订单数=("是否延迟交付", "sum"), 有效评分数=("交付评分", "count"),
        交付评分合计=("交付评分", "sum"), 投诉订单数=("有投诉", "sum"), 投诉工单数=("投诉工单数", "sum"),
    ).rename(columns={"交付月份": "月份"})
    public_lead = lead_cube.loc[lead_cube["线索数"] >= 10].copy()
    public_order = order_cube.loc[order_cube["有效订单数"] >= 10].copy()
    return lead_cube, order_cube, public_lead, public_order


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        h.update(path.name.encode("utf-8")); h.update(path.read_bytes())
    return h.hexdigest()


def write_public_outputs(
    bundle: CleanBundle, analysis: dict[str, Any], strategy: pd.DataFrame,
) -> dict[str, Any]:
    lead_cube, order_cube, public_lead, public_order = _aggregate_cubes(bundle.leads, bundle.orders)
    lead_cube.to_csv(PRIVATE_DIR / "dashboard_lead_cube.csv", index=False, encoding="utf-8-sig")
    order_cube.to_csv(PRIVATE_DIR / "dashboard_order_cube.csv", index=False, encoding="utf-8-sig")
    public_lead.to_csv(PUBLIC_DIR / "dashboard_lead_cube.csv", index=False, encoding="utf-8-sig")
    public_order.to_csv(PUBLIC_DIR / "dashboard_order_cube.csv", index=False, encoding="utf-8-sig")
    public_strategy = strategy.loc[strategy["线索数"] >= 10].copy()
    public_strategy.to_csv(PUBLIC_DIR / "W4_strategy_comparison.csv", index=False, encoding="utf-8-sig")
    write_json(PRIVATE_DIR / "analysis_results.json", analysis)
    write_json(PUBLIC_DIR / "analysis_results.json", analysis)
    public_files = [PUBLIC_DIR / "dashboard_lead_cube.csv", PUBLIC_DIR / "dashboard_order_cube.csv", PUBLIC_DIR / "W4_strategy_comparison.csv", PUBLIC_DIR / "analysis_results.json"]
    metadata = {
        "dataset_type": "public_sanitized_aggregate",
        "generated_at": datetime.now().astimezone().isoformat(),
        "data_as_of": str(bundle.leads["日期"].max().date()),
        "source_workbook_sha256": source_sha256(),
        "public_data_hash": _hash_files(public_files),
        "privacy": {
            "cell_suppression_threshold": 10,
            "lead_cells_suppressed": int(len(lead_cube) - len(public_lead)),
            "order_cells_suppressed": int(len(order_cube) - len(public_order)),
            "excluded_fields": ["线索ID", "订单ID", "销售员ID", "精确日期", "原始客户明细"],
        },
        "global_summary": {
            "线索数": int(bundle.leads["线索ID"].nunique()),
            "下订数": int(bundle.leads["是否下订"].sum()),
            "转化率": float(bundle.leads["是否下订"].mean()),
            "有效跟进线索数": int(bundle.leads["有效跟进线索"].sum()),
            "无关键冲突订单数": int((~bundle.orders["关键冲突"]).sum()),
        },
        "metric_definitions": {
            "每百线索订单数": "下订数 / 线索数 × 100；不是 ROI。",
            "延迟交付率": "无关键冲突订单中的延迟订单数 / 有效订单数。",
            "交付评分": "无关键冲突订单的加权平均交付评分。",
        },
    }
    write_json(PUBLIC_DIR / "dashboard_metadata.json", metadata)
    write_json(PRIVATE_DIR / "dashboard_metadata.json", {**metadata, "dataset_type": "local_complete_aggregate"})
    return metadata


def run_analysis(bundle: CleanBundle | None = None, publish: bool = True) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    if bundle is None:
        bundle = build_clean_data(save=True)
    psm, psm_charts = run_psm(bundle.leads)
    delivery, delivery_chart = run_delivery_analysis(bundle.orders)
    channel, channel_charts = run_channel_analysis(bundle.leads)
    model, model_importance = run_conversion_model(bundle.leads)
    analysis = {
        "schema_version": "1.0.0", "generated_at": datetime.now().astimezone().isoformat(),
        "source_sha256": source_sha256(), "psm": psm, "delivery": delivery, "channel": channel, "model": model,
        "interpretation_rules": {
            "significance": "A result is not described as reliable positive evidence unless its 95% CI excludes zero and design diagnostics pass.",
            "causal_language": "Adjusted associations and predictive explanations are not described as causal effects.",
            "multiple_testing": "Exploratory subgroup comparisons require Benjamini-Hochberg FDR control before promotion to findings.",
        },
    }
    strategy = build_strategy(bundle.leads, model_importance)
    if publish:
        strategy.to_csv(PRIVATE_DIR / "W4_strategy_comparison.csv", index=False, encoding="utf-8-sig")
        write_public_outputs(bundle, analysis, strategy)
    charts = {**psm_charts, "delivery": delivery_chart, **{f"channel_{k}": v for k, v in channel_charts.items()}, "model_importance": model_importance, "strategy": strategy}
    return analysis, charts


def run_all_core() -> tuple[CleanBundle, dict[str, Any], dict[str, pd.DataFrame]]:
    bundle = build_clean_data(save=True)
    analysis, charts = run_analysis(bundle)
    return bundle, analysis, charts


if __name__ == "__main__":
    run_all_core()
    print("G9 core data and analysis pipeline completed")
