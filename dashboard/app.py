"""G9 销售运营证据看板。

本地优先读取 data/processed 下的完整派生汇总；公开部署只读取 data_demo
中的脱敏汇总。所有推断性文字和数值均来自 analysis_results.json。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data_demo"
LOCAL_DIR = ROOT / "data" / "processed"

st.set_page_config(page_title="G9 智能销售运营决策", page_icon="◫", layout="wide")


def _secret(name: str) -> str | None:
    """Read Streamlit Secrets first; allow environment variables for local development."""
    try:
        value = st.secrets.get(name)
    except Exception:
        value = None
    return str(value) if value else os.getenv(name)


def require_login() -> None:
    expected = _secret("APP_PASSWORD")
    if not expected:
        st.error("应用尚未配置 APP_PASSWORD。请在 Streamlit Secrets 中配置后重新启动。")
        st.stop()
    if st.session_state.get("authenticated"):
        return
    st.title("G9 智能销售运营决策")
    st.caption("受保护的聚合分析看板")
    supplied = st.text_input("访问密码", type="password")
    if st.button("登录", type="primary", width="stretch"):
        if supplied == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码不正确。")
    st.stop()


@st.cache_data(show_spinner=False)
def load_dashboard_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict, str]:
    local_files = [
        LOCAL_DIR / "dashboard_lead_cube.csv",
        LOCAL_DIR / "dashboard_order_cube.csv",
        LOCAL_DIR / "analysis_results.json",
        LOCAL_DIR / "dashboard_metadata.json",
    ]
    base = LOCAL_DIR if all(p.exists() for p in local_files) else PUBLIC_DIR
    mode = "本地完整数据" if base == LOCAL_DIR else "公开脱敏汇总数据"
    lead = pd.read_csv(base / "dashboard_lead_cube.csv")
    order = pd.read_csv(base / "dashboard_order_cube.csv")
    strategy_path = base / "W4_strategy_comparison.csv"
    if not strategy_path.exists():
        strategy_path = PUBLIC_DIR / "W4_strategy_comparison.csv"
    strategy = pd.read_csv(strategy_path)
    results = json.loads((base / "analysis_results.json").read_text(encoding="utf-8"))
    metadata = json.loads((base / "dashboard_metadata.json").read_text(encoding="utf-8"))
    return lead, order, strategy, results, metadata, mode


def apply_filters(frame: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    out = frame.copy()
    for col, selected in filters.items():
        if col in out.columns and selected:
            out = out[out[col].astype(str).isin(selected)]
    return out


def pct(value: float | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{100 * value:.{digits}f}%"


def pp(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{100 * value:+.2f}pp"


def evidence_text(record: dict, unit: str = "pp") -> str:
    ci = record.get("ci95", [None, None])
    if record.get("estimate") is None:
        return "当前数据不满足识别条件"
    if unit == "score":
        return f"估计 {record['estimate']:+.3f} 分；95% CI [{ci[0]:+.3f} 分, {ci[1]:+.3f} 分]"
    return f"估计 {pp(record['estimate'])}；95% CI [{pp(ci[0])}, {pp(ci[1])}]"


def visible_metrics(lead: pd.DataFrame, order: pd.DataFrame) -> dict[str, float]:
    leads = float(lead["线索数"].sum()) if not lead.empty else 0
    booked = float(lead["下订数"].sum()) if not lead.empty else 0
    valid_orders = float(order["有效订单数"].sum()) if not order.empty else 0
    delayed = float(order["延迟订单数"].sum()) if not order.empty else 0
    ratings = float(order["有效评分数"].sum()) if not order.empty else 0
    rating_sum = float(order["交付评分合计"].sum()) if not order.empty else 0
    return {
        "leads": leads,
        "booked": booked,
        "conversion": booked / leads if leads else float("nan"),
        "valid_orders": valid_orders,
        "delay_rate": delayed / valid_orders if valid_orders else float("nan"),
        "rating": rating_sum / ratings if ratings else float("nan"),
    }


require_login()
lead_cube, order_cube, strategy, results, metadata, data_mode = load_dashboard_data()

st.markdown(
    """
    <style>
    .block-container{padding-top:1.7rem;max-width:1480px}
    [data-testid='stMetric']{background:#f7f8fa;border:1px solid #e7e9ee;padding:14px;border-radius:12px}
    .evidence{border-left:4px solid #2563eb;background:#f4f7ff;padding:12px 16px;border-radius:6px}
    </style>
    """,
    unsafe_allow_html=True,
)

head, badge = st.columns([4, 1])
with head:
    st.title("G9 智能销售运营决策")
    st.caption("统一口径 · 因果证据分级 · 公开数据隐私保护")
with badge:
    st.info(data_mode)

with st.sidebar:
    st.subheader("筛选")
    month = st.multiselect("月份", sorted(lead_cube["月份"].astype(str).unique()))
    city = st.multiselect("城市", sorted(lead_cube["城市"].astype(str).unique()))
    channel = st.multiselect("渠道", sorted(lead_cube["渠道"].astype(str).unique()))
    gender = st.multiselect("性别", sorted(lead_cube["性别"].astype(str).unique()))
    age = st.multiselect("年龄段", sorted(lead_cube["年龄段"].astype(str).unique()))
    st.divider()
    st.caption(f"数据截止：{metadata.get('data_as_of', '—')}")
    st.caption(f"生成时间：{metadata.get('generated_at', '—')[:19]}")
    st.caption(f"数据哈希：{metadata.get('public_data_hash', metadata.get('data_hash', '—'))[:16]}…")
    st.caption("公开汇总对样本量小于 10 的交叉单元执行抑制。")

lead_filtered = apply_filters(lead_cube, {"月份": month, "城市": city, "渠道": channel, "性别": gender, "年龄段": age})
order_filtered = apply_filters(order_cube, {"月份": month, "城市": city, "渠道": channel})
metrics = visible_metrics(lead_filtered, order_filtered)

tabs = st.tabs(["运营全景", "渠道分析", "预测中心", "风险预警", "销售团队", "策略推荐"])

with tabs[0]:
    if data_mode == "公开脱敏汇总数据":
        st.warning("以下筛选结果是未被抑制单元的可见合计；全局 KPI 使用元数据中的完整总体汇总。")
    summary = metadata.get("global_summary", {})
    no_filter = not any([month, city, channel, gender, age])
    global_metrics = {
        "leads": summary.get("线索数", metrics["leads"]),
        "booked": summary.get("下订数", metrics["booked"]),
        "conversion": summary.get("转化率", metrics["conversion"]),
        "valid_orders": summary.get("无关键冲突订单数", metrics["valid_orders"]),
    } if no_filter else metrics
    cols = st.columns(5)
    cols[0].metric("线索数", f"{global_metrics['leads']:,.0f}")
    cols[1].metric("下订数", f"{global_metrics['booked']:,.0f}")
    cols[2].metric("转化率", pct(global_metrics["conversion"]))
    cols[3].metric("无冲突有效订单", f"{global_metrics['valid_orders']:,.0f}")
    cols[4].metric("可见订单平均评分", f"{metrics['rating']:.2f}" if pd.notna(metrics["rating"]) else "—")

    monthly = lead_filtered.groupby("月份", as_index=False)[["线索数", "下订数"]].sum()
    if not monthly.empty:
        monthly["转化率"] = monthly["下订数"] / monthly["线索数"]
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(monthly, x="月份", y=["线索数", "下订数"], barmode="group", title="线索与下订趋势"), width="stretch")
        c2.plotly_chart(px.line(monthly, x="月份", y="转化率", markers=True, title="可见单元转化率趋势"), width="stretch")

    psm = results["psm"]["psm_att"]
    st.markdown(f"<div class='evidence'><b>面谈跟进证据：</b>{evidence_text(psm)}。平衡诊断：{psm['balance_status']}；证据等级：{psm['evidence_level']}。</div>", unsafe_allow_html=True)

with tabs[1]:
    channel_view = lead_filtered.groupby("渠道", as_index=False)[["线索数", "下订数"]].sum()
    channel_view["每百线索订单数"] = channel_view["下订数"].div(channel_view["线索数"]).mul(100)
    standardized = pd.DataFrame(results["channel"]["standardized"])
    channel_view = channel_view.merge(standardized, on="渠道", how="left")
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(channel_view, x="渠道", y="线索数", title="渠道线索规模"), width="stretch")
    c2.plotly_chart(px.bar(channel_view, x="渠道", y="每百线索订单数", title="每百线索订单数（不是 ROI）"), width="stretch")
    st.dataframe(channel_view.style.format({"每百线索订单数": "{:.2f}", "标准化边际转化率": "{:.2%}"}), width="stretch", hide_index=True)
    st.info("数据为单一获客渠道，不具备多触点路径；标准化边际转化率与模型特征贡献均不代表渠道因果贡献。费用只有城市—月份总额，因此不计算渠道 ROI/CPO。")

with tabs[2]:
    model = results["model"]
    if data_mode == "公开脱敏汇总数据":
        st.warning("公开模式已关闭逐客户预测和客户级导出。这里只展示经审核的总体模型表现。")
    m = model["metrics"]
    c1, c2, c3 = st.columns(3)
    c1.metric("时间外 ROC AUC", f"{m['roc_auc']:.3f}")
    c2.metric("时间外 PR AUC", f"{m['pr_auc']:.3f}")
    c3.metric("Brier Score", f"{m['brier_score']:.3f}")
    st.caption(f"训练样本 {m['train_size']:,}；验证样本 {m['test_size']:,}；验证起点 {m['test_start']}。")
    st.info("模型仅使用下订前可用基线特征，并按时间顺序训练/验证。当前区分度接近随机水平，仅适合风险分层研究，不应自动触发客户级运营动作。原‘生存分析’已停用，因为缺少真实事件时间。")
    imp = pd.DataFrame(model.get("feature_importance", []))
    if not imp.empty:
        feature_col = "feature" if "feature" in imp.columns else ("特征" if "特征" in imp.columns else imp.columns[0])
        value_col = next((c for c in imp.columns if c not in {feature_col, "标准差"}), None)
        if value_col:
            st.plotly_chart(px.bar(imp.head(15), x=value_col, y=feature_col, orientation="h", title="预测特征贡献（不代表因果）"), width="stretch")

with tabs[3]:
    risk = order_filtered.groupby(["城市", "月份"], as_index=False)[["有效订单数", "延迟订单数", "投诉订单数"]].sum()
    if not risk.empty:
        risk["延迟率"] = risk["延迟订单数"] / risk["有效订单数"]
        risk["投诉订单率"] = risk["投诉订单数"] / risk["有效订单数"]
        risk["风险等级"] = pd.cut(risk["延迟率"], [-0.01, .35, .55, 1.01], labels=["低", "中", "高"])
        st.plotly_chart(px.scatter(risk, x="延迟率", y="投诉订单率", size="有效订单数", color="风险等级", hover_data=["城市", "月份"], title="聚合交付风险分层"), width="stretch")
        st.dataframe(risk.style.format({"延迟率": "{:.1%}", "投诉订单率": "{:.1%}"}), width="stretch", hide_index=True)
    delivery = results["delivery"]["delivery_score_adjusted_association"]
    rdd = results["delivery"]["rdd_feasibility"]
    st.markdown(f"<div class='evidence'><b>延迟与评分：</b>{evidence_text(delivery, unit='score')}；证据等级：{delivery['evidence_level']}。<br><b>RDD 审计：</b>{rdd['evidence_level']}，未生成断点结论。</div>", unsafe_allow_html=True)

with tabs[4]:
    team = lead_filtered.groupby("城市", as_index=False)[["线索数", "下订数", "有效跟进线索数", "跟进次数合计"]].sum()
    if not team.empty:
        team["有效跟进覆盖率"] = team["有效跟进线索数"] / team["线索数"]
        team["人均线索跟进次数"] = team["跟进次数合计"] / team["有效跟进线索数"]
        team["转化率"] = team["下订数"] / team["线索数"]
        st.plotly_chart(px.bar(team, x="城市", y=["有效跟进覆盖率", "转化率"], barmode="group", title="城市跟进覆盖与转化"), width="stretch")
        st.dataframe(team.style.format({"有效跟进覆盖率": "{:.1%}", "人均线索跟进次数": "{:.2f}", "转化率": "{:.1%}"}), width="stretch", hide_index=True)
    st.caption("仅统计销售人员入职后且不晚于交付日期的有效跟进；公开模式不展示销售人员或客户明细。")

with tabs[5]:
    view = strategy.copy()
    if city:
        view = view[view["城市"].astype(str).isin(city)]
    if channel:
        view = view[view["渠道"].astype(str).isin(channel)]
    st.subheader("机会优先级")
    st.dataframe(view.head(30).style.format({"转化率": "{:.1%}", "跟进覆盖率": "{:.1%}", "机会量": "{:.1f}", "优先级分": "{:.1f}"}), width="stretch", hide_index=True)
    att = results["psm"]["psm_att"]
    ci = att["ci95"]
    if att["balance_status"] != "passed" or ci[0] <= 0 <= ci[1]:
        st.warning("面谈跟进的置信区间跨零：未发现可靠增益证据。建议补充下订时间戳，并通过随机实验或准实验验证后再调整流程。")
    st.info("优先级基于线索量、调整后转化表现、跟进覆盖与机会规模；不包含渠道 ROI、CPO 或预算增减百分比。")

with st.expander("方法、口径与版本说明"):
    st.json({
        "数据模式": data_mode,
        "数据截止": metadata.get("data_as_of"),
        "生成时间": metadata.get("generated_at"),
        "源数据哈希": metadata.get("source_workbook_sha256"),
        "公开数据哈希": metadata.get("public_data_hash"),
        "隐私规则": metadata.get("privacy"),
        "面谈方法": results["psm"]["psm_att"]["method"],
        "交付方法": results["delivery"]["delivery_score_adjusted_association"]["method"],
    })
