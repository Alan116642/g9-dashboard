from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import g9_pipeline as gp
from visual_catalog import WHITEPAPER_CHART_SEQUENCE, WHITEPAPER_TASK_CHART_KEYS, WHITEPAPER_TASK_SECTIONS
from visual_semantics import GOOD, IMPROVE, WATCH, classify_relative


REQUIRED_RESULT_KEYS = {
    "estimand", "estimate", "standard_error", "ci95", "p_value", "sample_size",
    "method", "balance_status", "assumptions", "evidence_level", "data_as_of",
}


def synthetic_leads(effect: float, seed: int = 7, n: int = 1200) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    treatment = rng.binomial(1, 0.35, n)
    base = 0.25 + 0.002 * (rng.normal(40, 8, n) - 40)
    outcome = rng.binomial(1, np.clip(base + effect * treatment, 0.02, 0.95))
    dates = pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 180, n), unit="D")
    return pd.DataFrame({
        "有效跟进线索": 1,
        "处理模糊": False,
        "面谈处理": treatment,
        "是否下订": outcome,
        "客户年龄": rng.normal(40, 8, n),
        "试驾时长": rng.normal(32, 7, n),
        "客户性别": rng.choice(["男", "女"], n),
        "城市": rng.choice(["上海", "北京", "深圳"], n),
        "月份": dates.to_period("M").astype(str),
        "渠道": rng.choice(["官网", "门店", "朋友推荐"], n),
        "日期": dates,
    })


def test_result_contract_is_complete():
    record = gp.result_record(
        estimand="test", estimate=0.0, standard_error=0.1, ci95=[-0.2, 0.2],
        p_value=1.0, sample_size=20, method="synthetic", balance_status="passed",
        assumptions=["none"], evidence_level="test", data_as_of="2025-01-01",
    )
    assert REQUIRED_RESULT_KEYS == set(record)


def test_null_effect_is_not_promoted(monkeypatch):
    monkeypatch.setattr(gp, "BOOTSTRAPS", 250)
    result, _ = gp.run_psm(synthetic_leads(0.0, seed=31))
    att = result["psm_att"]
    assert att["ci95"][0] <= 0 <= att["ci95"][1]
    assert att["evidence_level"] == "conditional_causal_no_reliable_gain"


def test_known_effect_recovers_positive_direction(monkeypatch):
    monkeypatch.setattr(gp, "BOOTSTRAPS", 250)
    result, _ = gp.run_psm(synthetic_leads(0.20, seed=19, n=1800))
    att = result["psm_att"]
    assert att["estimate"] > 0.10
    assert abs(att["estimate"] - 0.20) < 0.10


def test_rdd_is_blocked_without_valid_assignment_variable():
    import json
    results = json.loads((ROOT / "data_demo" / "analysis_results.json").read_text(encoding="utf-8"))
    rdd = results["delivery"]["rdd_feasibility"]
    assert rdd["estimate"] is None
    assert rdd["balance_status"] == "failed_design"
    assert rdd["evidence_level"] == "not_identified"


def test_whitepaper_visual_catalog_has_expanded_chinese_volume():
    keys = [item["key"] for item in WHITEPAPER_CHART_SEQUENCE]
    assert len(keys) == 54
    assert len(keys) == len(set(keys))
    assert {"effects", "delivery", "channel_raw_vs_standardized", "strategy", "business_funnel", "monthly_complaint_rate"}.issubset(keys)
    visible_copy = " ".join(item["caption"] + item["note"] for item in WHITEPAPER_CHART_SEQUENCE)
    assert not any(term in visible_copy for term in ["ROI", "PSM", "AIPW", "Wilson", "ROC", "AUC", "SMD", "ATT"])
    assert list(WHITEPAPER_TASK_SECTIONS) == [
        "W1 数据清洗与数据仓库建设",
        "W2 因果推断与归因分析",
        "W3 预测建模与智能预警",
        "W4 策略仿真与优化",
        "W5 决策看板与落地汇报",
    ]
    assert all(len(chart_keys) >= 8 for chart_keys in WHITEPAPER_TASK_CHART_KEYS.values())
    assert [item["section"] for item in WHITEPAPER_CHART_SEQUENCE] == [
        task for task, chart_keys in WHITEPAPER_TASK_CHART_KEYS.items() for _ in chart_keys
    ]


def test_action_colors_follow_metric_direction():
    assert classify_relative([10, 20, 30], "higher") == [IMPROVE, WATCH, GOOD]
    assert classify_relative([10, 20, 30], "lower") == [GOOD, WATCH, IMPROVE]


def test_dashboard_renders_six_pages_and_40_charts(monkeypatch):
    from streamlit.testing.v1 import AppTest

    password = "dashboard-smoke-test-password"
    monkeypatch.setenv("APP_PASSWORD", password)
    app = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=120).run()
    app.text_input[0].set_value(password)
    app.button[0].click().run(timeout=120)

    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["运营全景", "渠道分析", "预测中心", "风险预警", "销售团队", "策略推荐"]
    assert len(app.get("plotly_chart")) == 40
