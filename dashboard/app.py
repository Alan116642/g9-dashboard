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


def lead_rollup(frame: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Aggregate the public lead cube without duplicating lead counts."""
    metrics = ["线索数", "下订数", "有效跟进线索数", "跟进次数合计"]
    out = frame.groupby(dimensions, as_index=False)[metrics].sum()
    out["转化率"] = out["下订数"].div(out["线索数"].replace(0, pd.NA))
    out["有效跟进覆盖率"] = out["有效跟进线索数"].div(out["线索数"].replace(0, pd.NA))
    out["每百线索订单数"] = out["转化率"] * 100
    out["每条有效跟进线索跟进次数"] = out["跟进次数合计"].div(out["有效跟进线索数"].replace(0, pd.NA))
    return out


def order_rollup(frame: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Aggregate the public order cube at a requested reporting grain."""
    metrics = ["有效订单数", "延迟订单数", "有效评分数", "交付评分合计", "投诉订单数"]
    out = frame.groupby(dimensions, as_index=False)[metrics].sum()
    denominator = out["有效订单数"].replace(0, pd.NA)
    out["延迟率"] = out["延迟订单数"].div(denominator)
    out["投诉订单率"] = out["投诉订单数"].div(denominator)
    out["平均交付评分"] = out["交付评分合计"].div(out["有效评分数"].replace(0, pd.NA))
    return out


def polish(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=55, b=22),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend_title_text="",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E5E7EB", zerolinecolor="#CBD5E1")
    return fig


_chart_index = 0


def render_chart(container, fig: go.Figure, *, height: int = 360) -> None:
    """Render every Plotly figure with a deterministic unique Streamlit key."""
    global _chart_index
    _chart_index += 1
    container.plotly_chart(polish(fig, height=height), width="stretch", key=f"analysis-chart-{_chart_index:02d}")


def render_pair(left: go.Figure, right: go.Figure) -> None:
    c1, c2 = st.columns(2)
    render_chart(c1, left)
    render_chart(c2, right)


def heatmap(frame: pd.DataFrame, index: str, columns: str, values: str, title: str, percent: bool = False) -> go.Figure:
    pivot = frame.pivot(index=index, columns=columns, values=values)
    texttemplate = ".1%" if percent else ",.0f"
    fig = px.imshow(pivot, text_auto=texttemplate, aspect="auto", color_continuous_scale="Blues", title=title)
    fig.update_layout(coloraxis_colorbar_title="比例" if percent else "数量")
    return fig


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
    st.caption("统一口径 · 因果证据分级 · 公开数据隐私保护 · 六页共 40 个分析图")
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

    monthly = lead_rollup(lead_filtered, ["月份"]).sort_values("月份")
    if not monthly.empty:
        st.subheader("规模与转化趋势")
        render_pair(
            px.bar(monthly, x="月份", y=["线索数", "下订数"], barmode="group", title="月度线索与下订规模"),
            px.line(monthly, x="月份", y="转化率", markers=True, title="月度转化率"),
        )
        render_pair(
            px.line(monthly, x="月份", y="有效跟进覆盖率", markers=True, title="月度有效跟进覆盖率"),
            px.line(monthly, x="月份", y="每条有效跟进线索跟进次数", markers=True, title="月度有效跟进频次"),
        )

    city_view = lead_rollup(lead_filtered, ["城市"])
    age_view = lead_rollup(lead_filtered, ["年龄段"])
    gender_view = lead_rollup(lead_filtered, ["性别"])
    if not city_view.empty:
        st.subheader("城市与客户结构")
        render_pair(
            px.bar(city_view.sort_values("线索数", ascending=False), x="城市", y="线索数", title="城市线索规模"),
            px.bar(city_view.sort_values("转化率", ascending=False), x="城市", y="转化率", title="城市转化率（描述性）"),
        )
    if not age_view.empty and not gender_view.empty:
        render_pair(
            px.bar(age_view, x="年龄段", y="转化率", title="年龄段转化率（描述性）"),
            px.bar(gender_view, x="性别", y="转化率", title="性别转化率（描述性）"),
        )
    city_month = lead_rollup(lead_filtered, ["城市", "月份"])
    if not city_month.empty:
        render_pair(
            heatmap(city_month, "城市", "月份", "线索数", "城市-月份线索量矩阵"),
            heatmap(city_month, "城市", "月份", "转化率", "城市-月份转化率矩阵", percent=True),
        )

    psm = results["psm"]["psm_att"]
    st.markdown(f"<div class='evidence'><b>面谈跟进证据：</b>{evidence_text(psm)}。平衡诊断：{psm['balance_status']}；证据等级：{psm['evidence_level']}。</div>", unsafe_allow_html=True)

with tabs[1]:
    channel_view = lead_rollup(lead_filtered, ["渠道"])
    standardized = pd.DataFrame(results["channel"]["standardized"])
    channel_view = channel_view.merge(standardized, on="渠道", how="left")
    st.subheader("渠道规模与转化")
    render_pair(
        px.bar(channel_view.sort_values("线索数", ascending=False), x="渠道", y="线索数", title="渠道线索规模"),
        px.bar(channel_view.sort_values("每百线索订单数", ascending=False), x="渠道", y="每百线索订单数", title="每百线索订单数（不是 ROI）"),
    )
    render_pair(
        px.bar(channel_view.sort_values("有效跟进覆盖率", ascending=False), x="渠道", y="有效跟进覆盖率", title="渠道有效跟进覆盖率"),
        px.bar(channel_view, x="渠道", y=["转化率", "标准化边际转化率"], barmode="group", title="原始与标准化转化率（关联性）"),
    )
    city_channel = lead_rollup(lead_filtered, ["城市", "渠道"])
    month_channel = lead_rollup(lead_filtered, ["月份", "渠道"])
    if not city_channel.empty and not month_channel.empty:
        render_pair(
            heatmap(city_channel, "城市", "渠道", "转化率", "城市-渠道转化率矩阵", percent=True),
            heatmap(month_channel, "月份", "渠道", "转化率", "月份-渠道转化率矩阵", percent=True),
        )
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
            imp["绝对预测重要性"] = imp[value_col].abs()
            split = pd.DataFrame({"样本": ["训练", "时间外验证"], "数量": [m["train_size"], m["test_size"]]})
            st.subheader("时间外模型诊断")
            render_pair(
                px.bar(imp.sort_values(value_col), x=value_col, y=feature_col, error_x="标准差" if "标准差" in imp.columns else None, orientation="h", title="预测特征贡献及不确定性（非因果）"),
                px.bar(imp.sort_values("绝对预测重要性"), x="绝对预测重要性", y=feature_col, orientation="h", title="绝对预测重要性排序（非因果）"),
            )
            render_chart(st, px.bar(split, x="样本", y="数量", text_auto=True, title="时间顺序训练与验证样本量"))

with tabs[3]:
    risk = order_rollup(order_filtered, ["城市", "月份"])
    if not risk.empty:
        risk["风险等级"] = pd.cut(risk["延迟率"], [-0.01, .35, .55, 1.01], labels=["低", "中", "高"])
        st.subheader("聚合交付风险")
        render_chart(st, px.scatter(risk, x="延迟率", y="投诉订单率", size="有效订单数", color="风险等级", hover_data=["城市", "月份"], title="城市-月份延迟与投诉风险（聚合关联）"), height=430)
        city_risk = order_rollup(order_filtered, ["城市"])
        month_risk = order_rollup(order_filtered, ["月份"]).sort_values("月份")
        channel_risk = order_rollup(order_filtered, ["渠道"])
        render_pair(
            px.bar(city_risk.sort_values("延迟率", ascending=False), x="城市", y="延迟率", title="城市延迟交付率"),
            px.bar(city_risk.sort_values("平均交付评分", ascending=False), x="城市", y="平均交付评分", title="城市平均交付评分"),
        )
        render_chart(st, px.bar(city_risk.sort_values("投诉订单率", ascending=False), x="城市", y="投诉订单率", title="城市投诉订单率"))
        render_pair(
            px.line(month_risk, x="月份", y="延迟率", markers=True, title="月度延迟交付率"),
            px.line(month_risk, x="月份", y="平均交付评分", markers=True, title="月度平均交付评分"),
        )
        render_chart(st, px.line(month_risk, x="月份", y="投诉订单率", markers=True, title="月度投诉订单率"))
        render_pair(
            px.bar(channel_risk.sort_values("延迟率", ascending=False), x="渠道", y="延迟率", title="渠道来源订单延迟率（描述性）"),
            px.bar(channel_risk.sort_values("平均交付评分", ascending=False), x="渠道", y="平均交付评分", title="渠道来源订单平均评分（描述性）"),
        )
        render_chart(st, px.bar(channel_risk.sort_values("投诉订单率", ascending=False), x="渠道", y="投诉订单率", title="渠道来源订单投诉率（描述性）"))
        st.dataframe(risk.style.format({"延迟率": "{:.1%}", "投诉订单率": "{:.1%}"}), width="stretch", hide_index=True)
    delivery = results["delivery"]["delivery_score_adjusted_association"]
    rdd = results["delivery"]["rdd_feasibility"]
    st.markdown(f"<div class='evidence'><b>延迟与评分：</b>{evidence_text(delivery, unit='score')}；证据等级：{delivery['evidence_level']}。<br><b>RDD 审计：</b>{rdd['evidence_level']}，未生成断点结论。</div>", unsafe_allow_html=True)

with tabs[4]:
    team = lead_rollup(lead_filtered, ["城市"])
    if not team.empty:
        st.subheader("有效跟进覆盖与容量")
        render_pair(
            px.bar(team, x="城市", y=["有效跟进覆盖率", "转化率"], barmode="group", title="城市跟进覆盖与转化"),
            px.bar(team.sort_values("每条有效跟进线索跟进次数", ascending=False), x="城市", y="每条有效跟进线索跟进次数", title="城市有效跟进频次"),
        )
        month_team = lead_rollup(lead_filtered, ["月份"]).sort_values("月份")
        channel_team = lead_rollup(lead_filtered, ["渠道"])
        render_pair(
            px.line(month_team, x="月份", y="有效跟进覆盖率", markers=True, title="月度有效跟进覆盖率"),
            px.line(month_team, x="月份", y="每条有效跟进线索跟进次数", markers=True, title="月度有效跟进频次"),
        )
        render_chart(st, px.bar(channel_team.sort_values("有效跟进覆盖率", ascending=False), x="渠道", y="有效跟进覆盖率", title="渠道有效跟进覆盖率"))
        st.dataframe(team.style.format({"有效跟进覆盖率": "{:.1%}", "每条有效跟进线索跟进次数": "{:.2f}", "转化率": "{:.1%}"}), width="stretch", hide_index=True)
    st.caption("仅统计销售人员入职后且不晚于交付日期的有效跟进；公开模式不展示销售人员或客户明细。")

with tabs[5]:
    view = strategy.copy()
    if city:
        view = view[view["城市"].astype(str).isin(city)]
    if channel:
        view = view[view["渠道"].astype(str).isin(channel)]
    st.subheader("机会优先级")
    if not view.empty:
        ranked = view.sort_values("优先级分", ascending=False).head(15).copy()
        ranked["组合"] = ranked["城市"].astype(str) + " / " + ranked["渠道"].astype(str)
        render_pair(
            px.bar(ranked.sort_values("优先级分"), x="优先级分", y="组合", orientation="h", title="城市-渠道机会优先级"),
            px.bar(ranked.sort_values("机会量"), x="机会量", y="组合", orientation="h", title="城市-渠道机会量"),
        )
        render_chart(st, px.scatter(view, x="跟进覆盖率", y="转化率", size="线索数", color="渠道", hover_data=["城市", "优先级分"], title="转化率与跟进覆盖的机会分布"), height=430)
        city_priority = view.groupby("城市", as_index=False).agg(平均优先级分=("优先级分", "mean"), 机会量=("机会量", "sum"))
        channel_priority = view.groupby("渠道", as_index=False).agg(平均优先级分=("优先级分", "mean"), 机会量=("机会量", "sum"))
        render_pair(
            px.bar(city_priority.sort_values("平均优先级分", ascending=False), x="城市", y="平均优先级分", title="城市平均机会优先级"),
            px.bar(channel_priority.sort_values("平均优先级分", ascending=False), x="渠道", y="平均优先级分", title="渠道平均机会优先级（不是 ROI）"),
        )
        recommendations = view["建议"].value_counts().rename_axis("建议").reset_index(name="组合数")
        render_chart(st, px.bar(recommendations, x="组合数", y="建议", orientation="h", title="机会组合建议构成"))
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
