"""
G9 智能销售运营决策系统 — 全交互式Streamlit仪表盘 (增强版)
运行: python -m streamlit run dashboard/app.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os, sys, hmac, hashlib

sys.stdout.reconfigure(encoding='utf-8')

# ===== PASSWORD PROTECTION =====
def check_password():
    """密码保护：040102"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Login form
    st.markdown("""
    <style>
    .login-box { max-width: 400px; margin: 100px auto; padding: 40px;
        background: #fff; border-radius: 16px; box-shadow: 0 8px 40px rgba(0,0,0,0.1);
        text-align: center; }
    .login-title { font-size: 1.8rem; font-weight: 900; color: #2563EB; margin-bottom: 8px; }
    .login-sub { color: #6B7280; margin-bottom: 24px; }
    </style>
    <div class="login-box">
    <div class="login-title">G9 智能决策系统</div>
    <div class="login-sub">请输入访问密码</div>
    </div>
    """, unsafe_allow_html=True)

    password = st.text_input("", type="password", placeholder="输入密码", key="pwd_input")

    if st.button("登录", type="primary", use_container_width=True):
        # SHA256 hash comparison
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        correct_hash = hashlib.sha256("040102".encode()).hexdigest()
        if hmac.compare_digest(entered_hash, correct_hash):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码错误")

    return False

# ===== PAGE CONFIG =====
st.set_page_config(page_title="G9 智能决策系统", page_icon="🚗", layout="wide",
                   initial_sidebar_state="expanded")

# ===== ENHANCED CSS =====
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
.main-header { font-size: 2.2rem; font-weight: 900; background: linear-gradient(135deg, #2563EB, #7C3AED);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0; }
.kpi-row { display: flex; gap: 12px; flex-wrap: wrap; }
.kpi-card { flex: 1; min-width: 150px; border-radius: 16px; padding: 18px 16px; color: #fff;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08); transition: transform .15s; }
.kpi-card:hover { transform: translateY(-3px); }
.kpi-card.blue { background: linear-gradient(135deg, #2563EB, #3B82F6); }
.kpi-card.green { background: linear-gradient(135deg, #059669, #10B981); }
.kpi-card.orange { background: linear-gradient(135deg, #EA580C, #F97316); }
.kpi-card.red { background: linear-gradient(135deg, #DC2626, #EF4444); }
.kpi-card.purple { background: linear-gradient(135deg, #7C3AED, #8B5CF6); }
.kpi-card.teal { background: linear-gradient(135deg, #0D9488, #14B8A6); }
.kpi-value { font-size: 2rem; font-weight: 900; line-height: 1.1; }
.kpi-label { font-size: 0.8rem; opacity: 0.85; margin-top: 4px; }
.kpi-sub { font-size: 0.7rem; opacity: 0.7; }
.section-divider { margin: 2rem 0 1rem; border-top: 2px solid #E5E7EB; }
.chart-container { background: #fff; border-radius: 14px; padding: 18px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.04); margin-bottom: 16px; }
.insight-box { background: #F0F9FF; border-left: 4px solid #2563EB; border-radius: 8px;
    padding: 14px 18px; margin: 12px 0; font-size: 0.9rem; }
.insight-box.warn { background: #FFFBEB; border-left-color: #F59E0B; }
.insight-box.success { background: #F0FDF4; border-left-color: #10B981; }
</style>
""", unsafe_allow_html=True)

# ===== DATA LOADING =====
@st.cache_data(ttl=3600)
def load_data():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    private_path = os.path.join(base_dir, 'data', 'wide_table.csv')
    demo_path = os.path.join(base_dir, 'data_demo', 'wide_table.csv')
    path = private_path if os.path.exists(private_path) else demo_path
    if not os.path.exists(path): return None
    df = pd.read_csv(path)
    df['日期'] = pd.to_datetime(df['日期'])
    df['月份'] = df['日期'].dt.to_period('M').astype(str)
    df['星期'] = df['日期'].dt.dayofweek
    df['周几'] = df['日期'].dt.day_name()
    # Derived
    df['年龄分段'] = pd.cut(df['客户年龄'], bins=[0,25,35,45,55,100],
                          labels=['18-25','26-35','36-45','46-55','56+'])
    if '是否延迟交付' in df.columns:
        df['延迟标签'] = df['是否延迟交付'].map({1:'延迟', 0:'准时'}).fillna('未交付')
    return df

@st.cache_data(ttl=3600)
def load_strategy():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    private_path = os.path.join(base_dir, 'reports', 'W4_strategy_comparison.csv')
    demo_path = os.path.join(base_dir, 'data_demo', 'W4_strategy_comparison.csv')
    path = private_path if os.path.exists(private_path) else demo_path
    return pd.read_csv(path) if os.path.exists(path) else None

# ===== FILTER LOGIC =====
def apply_filters(df, date_range, cities, channels, age_range, genders):
    if df is None: return None
    d = df.copy()
    if date_range and len(date_range) == 2:
        d = d[(d['日期'] >= pd.Timestamp(date_range[0])) & (d['日期'] <= pd.Timestamp(date_range[1]))]
    if cities and '全部' not in cities:
        d = d[d['城市'].isin(cities)]
    if channels and '全部' not in channels:
        d = d[d['渠道'].isin(channels)]
    if age_range:
        d = d[(d['客户年龄'] >= age_range[0]) & (d['客户年龄'] <= age_range[1])]
    if genders and '全部' not in genders:
        d = d[d['客户性别'].isin(genders)]
    return d

# ===== SIDEBAR =====
def render_sidebar(df):
    st.sidebar.markdown('<p style="font-size:1.6rem;font-weight:900;">G9</p>', unsafe_allow_html=True)
    st.sidebar.markdown('<p style="color:#6B7280;margin-top:-15px;">智能销售运营决策系统</p>', unsafe_allow_html=True)
    st.sidebar.markdown("---")

    with st.sidebar.expander("📅 时间筛选", expanded=True):
        date_range = (df['日期'].min(), df['日期'].max()) if df is not None else None
        dr = st.date_input("日期范围", value=date_range,
                           min_value=date_range[0], max_value=date_range[1]) if date_range else None

    with st.sidebar.expander("🏙️ 城市 & 渠道", expanded=True):
        all_cities = ['全部'] + sorted(df['城市'].unique().tolist()) if df is not None else ['全部']
        cities = st.multiselect("城市", all_cities, default=['全部'], key='city_sel')
        all_ch = ['全部'] + sorted(df['渠道'].unique().tolist()) if df is not None else ['全部']
        channels = st.multiselect("渠道", all_ch, default=['全部'], key='ch_sel')

    with st.sidebar.expander("👤 客户筛选", expanded=False):
        age_range = st.slider("年龄范围", 18, 70, (18, 70))
        genders = st.multiselect("性别", ['全部','男','女'], default=['全部'])

    st.sidebar.markdown("---")

    if df is not None:
        filtered = apply_filters(df, dr if 'dr' in dir() else None, cities, channels, age_range, genders)
        st.sidebar.markdown(f"**筛选结果**: {len(filtered):,} 条线索")
        st.sidebar.markdown(f"**转化率**: {filtered['是否下订'].mean()*100:.1f}%")

    st.sidebar.markdown("---")
    st.sidebar.caption("数据仅本地处理 | 不外传 | v2.0")

    return dr if 'dr' in dir() else None, cities, channels, age_range, genders

# ===== TAB 1: 运营全景 =====
def render_overview(df):
    st.markdown('<p class="main-header">运营全景</p>', unsafe_allow_html=True)

    # --- KPI ROW ---
    n = len(df)
    cvr = df['是否下订'].mean()
    orders = df[df['订单ID'].notna()]
    n_orders = orders['订单ID'].nunique()
    delay_rate = orders['是否延迟交付'].mean() if len(orders) > 0 else 0
    del_score = orders['交付评分'].mean() if len(orders) > 0 else 0
    as_data = df[df['售后平均满意度'] > 0]
    as_sat = as_data['售后平均满意度'].mean() if len(as_data) > 0 else 0
    fu_rate = (df['跟进总次数'] > 0).mean()
    avg_followup = df[df['跟进总次数'] > 0]['跟进总次数'].mean()
    avg_testdrive = df['试驾时长'].mean()

    kpis = [
        ("线索总量", f"{n:,}", f"跟进率 {fu_rate*100:.0f}%", "blue"),
        ("转化率", f"{cvr*100:.1f}%", f"订单 {n_orders:,}", "green"),
        ("延迟交付率", f"{delay_rate*100:.1f}%", f"交付评分 {del_score:.2f}", "orange"),
        ("售后满意度", f"{as_sat:.2f}/5", f"投诉率 {df['是否有投诉'].mean()*100:.1f}%", "red"),
        ("平均试驾时长", f"{avg_testdrive:.0f}分钟", f"跟进 {avg_followup:.1f}次/人", "purple"),
        ("线索月份范围", f"{df['月份'].nunique()}个月", f"覆盖 {df['城市'].nunique()} 城市", "teal"),
    ]

    cols = st.columns(6)
    for col, (label, val, sub, color) in zip(cols, kpis):
        with col:
            st.markdown(f"""<div class="kpi-card {color}">
            <div class="kpi-value">{val}</div><div class="kpi-label">{label}</div>
            <div class="kpi-sub">{sub}</div></div>""", unsafe_allow_html=True)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # --- ROW 1: Trend + City Map ---
    c1, c2 = st.columns([1.2, 0.8])
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("📈 月度趋势 (线索·订单·转化率)")
        monthly = df.groupby('月份').agg(线索=('线索ID','count'), 订单=('是否下订','sum')).reset_index()
        monthly['转化率'] = monthly['订单'] / monthly['线索'] * 100
        monthly = monthly.sort_values('月份')
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=monthly['月份'], y=monthly['线索'], name='线索量',
                            marker_color='#93C5FD', marker_line_color='#2563EB', marker_line_width=1), secondary_y=False)
        fig.add_trace(go.Scatter(x=monthly['月份'], y=monthly['订单'], name='订单量',
                                mode='lines+markers', line=dict(color='#10B981', width=3.5),
                                marker=dict(size=10, color='#059669')), secondary_y=False)
        fig.add_trace(go.Scatter(x=monthly['月份'], y=monthly['转化率'], name='转化率%',
                                mode='lines+markers', line=dict(color='#F97316', width=2, dash='dot'),
                                marker=dict(size=7, symbol='diamond')), secondary_y=True)
        fig.update_layout(height=420, hovermode='x unified', legend=dict(orientation='h', y=1.1),
                          margin=dict(l=10,r=10,t=30,b=10))
        fig.update_yaxes(title_text="数量", secondary_y=False)
        fig.update_yaxes(title_text="转化率 %", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("🌍 城市表现矩阵")
        city_stats = df.groupby('城市').agg(线索量=('线索ID','count'), 转化率=('是否下订','mean'),
                                           订单=('是否下订','sum'), 平均试驾=('试驾时长','mean')).reset_index()
        city_stats['转化率%'] = city_stats['转化率'] * 100
        fig = px.scatter(city_stats, x='线索量', y='转化率%', size='订单', color='城市',
                         text='城市', size_max=45, height=420,
                         color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_traces(textposition='top center', marker=dict(line=dict(width=1, color='white')))
        fig.update_layout(showlegend=False, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- ROW 2: Funnel + Age/Config ---
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("🔄 全链路转化漏斗")
        stages = ['线索', '有跟进', '已下订', f'已交付\n({n_orders}单)', '有投诉']
        vals = [n, int((df['跟进总次数']>0).sum()), int(df['是否下订'].sum()),
                n_orders, int(df['是否有投诉'].sum())]
        fig = go.Figure(go.Funnel(y=stages, x=vals, textposition="inside",
                        textinfo="value+percent previous", textfont=dict(size=13),
                        marker=dict(color=['#2563EB','#3B82F6','#10B981','#F59E0B','#EF4444'],
                                    line=dict(width=1, color='white'))))
        fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("🚙 配置×年龄 转化热力图")
        heat = df.pivot_table(values='是否下订', index='年龄分段', columns='配置' if '配置' in df.columns else '渠道',
                              aggfunc='mean') * 100
        fig = px.imshow(heat, text_auto='.1f', aspect='auto', color_continuous_scale='RdYlGn',
                        range_color=[15, 45], height=380)
        fig.update_layout(margin=dict(l=10,r=10,t=30,b=10))
        fig.update_coloraxes(colorbar_title='转化率%')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- ROW 3: Daily + Weekday pattern ---
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("📅 每日线索趋势 (7日移动平均)")
        daily = df.groupby('日期').agg(线索=('线索ID','count'), 订单=('是否下订','sum')).reset_index().sort_values('日期')
        daily['线索MA'] = daily['线索'].rolling(7).mean()
        daily['订单MA'] = daily['订单'].rolling(7).mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily['日期'], y=daily['线索'], mode='markers', name='日线索',
                                 marker=dict(size=2, color='#93C5FD'), opacity=0.5))
        fig.add_trace(go.Scatter(x=daily['日期'], y=daily['线索MA'], mode='lines', name='线索7日MA',
                                 line=dict(color='#2563EB', width=3)))
        fig.add_trace(go.Scatter(x=daily['日期'], y=daily['订单MA'], mode='lines', name='订单7日MA',
                                 line=dict(color='#10B981', width=2.5)))
        fig.update_layout(height=350, hovermode='x', legend=dict(orientation='h'),
                          margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("📊 周几线索分布")
        weekday_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        weekday_cn = ['周一','周二','周三','周四','周五','周六','周日']
        wk = df.groupby('周几').agg(线索=('线索ID','count'), 转化率=('是否下订','mean')).reindex(weekday_order)
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=weekday_cn, y=wk['线索'], name='线索量', marker_color='#2563EB',
                            text=wk['线索'].values, textposition='outside'), secondary_y=False)
        fig.add_trace(go.Scatter(x=weekday_cn, y=wk['转化率']*100, name='转化率%',
                                mode='lines+markers', line=dict(color='#F97316', width=3),
                                marker=dict(size=10)), secondary_y=True)
        fig.update_layout(height=350, legend=dict(orientation='h'), margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Insight Box ---
    top_city = df.groupby('城市')['是否下订'].mean().idxmax()
    top_ch = df.groupby('渠道')['是否下订'].mean().idxmax()
    st.markdown(f"""<div class="insight-box">
    💡 <b>关键洞察</b>: 转化率最高的城市是 <b>{top_city}</b>, 最高效渠道是 <b>{top_ch}</b>。
    线索量在周三达到峰值, 周末线索量下降明显。试驾时长与转化率呈正相关。</div>""", unsafe_allow_html=True)

# ===== TAB 2: 渠道归因 =====
def render_channels(df):
    st.markdown('<p class="main-header">渠道深度分析</p>', unsafe_allow_html=True)

    ch_stats = df.groupby('渠道').agg(
        线索量=('线索ID','count'), 订单量=('是否下订','sum'),
        转化率=('是否下订','mean'), 平均试驾=('试驾时长','mean'),
        平均跟进=('跟进总次数','mean')
    ).sort_values('线索量', ascending=False)
    ch_stats['转化率%'] = ch_stats['转化率'] * 100
    ch_stats['份额%'] = ch_stats['线索量'] / ch_stats['线索量'].sum() * 100

    # --- ROW 1 ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("转化率排名")
        ordered = ch_stats.sort_values('转化率%')
        fig = go.Figure(go.Bar(x=ordered['转化率%'], y=ordered.index, orientation='h',
                     text=[f'{v:.1f}%' for v in ordered['转化率%']], textposition='outside',
                     marker_color=['#2563EB' if v==ordered['转化率%'].max() else '#93C5FD' for v in ordered['转化率%']]))
        fig.update_layout(height=300, margin=dict(l=10,r=50,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("线索份额")
        fig = px.pie(ch_stats, values='线索量', names=ch_stats.index, hole=0.55,
                     color_discrete_sequence=px.colors.qualitative.Bold, height=300)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("ROI估算")
        ch_stats['ROI'] = ch_stats['订单量'] / (ch_stats['线索量'] / 100)
        ordered_r = ch_stats.sort_values('ROI')
        fig = go.Figure(go.Bar(x=ordered_r['ROI'], y=ordered_r.index, orientation='h',
                     text=[f'{v:.1f}' for v in ordered_r['ROI']], textposition='outside',
                     marker_color=['#10B981' if v==ordered_r['ROI'].max() else '#A7F3D0' for v in ordered_r['ROI']]))
        fig.update_layout(height=300, margin=dict(l=10,r=50,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- ROW 2 ---
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("城市×渠道 转化率热力图")
        pivot = df.pivot_table(values='是否下订', index='城市', columns='渠道', aggfunc='mean') * 100
        fig = px.imshow(pivot, text_auto='.1f', aspect='auto', color_continuous_scale='RdYlGn',
                        range_color=[10, 50], height=420)
        fig.update_layout(margin=dict(l=10,r=10,t=30,b=10))
        fig.update_coloraxes(colorbar_title='转化率%')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("渠道月度贡献趋势")
        mon_ch = df.pivot_table(values='线索ID', index='月份', columns='渠道', aggfunc='count').fillna(0)
        mon_ch = mon_ch.reindex(sorted(mon_ch.index))
        fig = px.area(mon_ch, x=mon_ch.index, y=mon_ch.columns, height=420,
                      color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(legend=dict(orientation='h', y=1.05), margin=dict(l=10,r=10,t=30,b=10),
                          yaxis_title='线索量', xaxis_title='')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Insight ---
    best_ch = ch_stats['转化率%'].idxmax()
    worst_ch = ch_stats['转化率%'].idxmin()
    st.markdown(f"""<div class="insight-box">
    💡 <b>渠道洞察</b>: <b>{best_ch}</b> 转化率最高 ({ch_stats['转化率%'].max():.1f}%)，
    但线索量占比仅 {ch_stats.loc[best_ch,'份额%']:.1f}%。<b>{worst_ch}</b> 转化率最低 ({ch_stats['转化率%'].min():.1f}%)，
    建议优化或减少投入。</div>""", unsafe_allow_html=True)

    # --- Channel detailed table ---
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.subheader("渠道综合指标表")
    display_df = ch_stats.reset_index().rename(columns={'渠道':'渠道','线索量':'线索量','订单量':'订单量',
                                        '转化率%':'转化率%','份额%':'线索份额%','平均试驾':'平均试驾(分)',
                                        '平均跟进':'平均跟进次数','ROI':'ROI指数'})
    st.dataframe(display_df.set_index('渠道').style.background_gradient(subset=['转化率%'], cmap='RdYlGn')
                 .format({'转化率%':'{:.1f}','线索份额%':'{:.1f}','平均试驾(分)':'{:.1f}',
                          '平均跟进次数':'{:.2f}','ROI指数':'{:.1f}'}), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ===== TAB 3: 预测中心 =====
def render_prediction(df):
    st.markdown('<p class="main-header">智能预测中心</p>', unsafe_allow_html=True)

    c_left, c_right = st.columns([0.35, 0.65])

    with c_left:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("🎯 客户特征输入")
        city = st.selectbox("城市", sorted(df['城市'].unique()), key='pred_city')
        channel = st.selectbox("渠道", sorted(df['渠道'].unique()), key='pred_ch')
        age = st.slider("客户年龄", 18, 70, 36, key='pred_age')
        gender = st.radio("性别", ['男', '女'], horizontal=True, key='pred_gender')
        test_drive = st.slider("试驾时长 (分钟)", 5, 60, 32, key='pred_td')
        followup = st.slider("预期跟进次数", 0, 10, 2, key='pred_fu')
        fu_method = st.selectbox("跟进方式", ['电话', '微信', '面谈'], key='pred_fum')

        pred_clicked = st.button("🔮 计算转化概率", type="primary", use_container_width=True)

        if pred_clicked:
            # Multi-factor prediction
            base = df['是否下订'].mean()
            c_eff = df[df['城市']==city]['是否下訂'].mean() if '是否下訂' in df.columns else df[df['城市']==city]['是否下订'].mean()
            ch_eff = df[df['渠道']==channel]['是否下订'].mean()
            age_f = -0.004 * abs(age - 38) + 0.02
            td_f = 0.0025 * (test_drive - 25)
            fu_f = 0.015 * min(followup, 5)
            method_bonus = 0.04 if fu_method == '面谈' else (0.01 if fu_method == '电话' else 0)
            prob = c_eff * 0.3 + ch_eff * 0.25 + base * 0.25 + age_f + td_f + fu_f + method_bonus
            prob = max(0.03, min(0.88, prob))

            st.markdown("---")
            fig = go.Figure(go.Indicator(mode="gauge+number+delta", value=prob*100,
                title={'text':"转化概率 %", 'font':{'size':16}},
                delta={'reference': base*100, 'increasing':{'color':'#10B981'}, 'decreasing':{'color':'#EF4444'}},
                gauge={'axis':{'range':[0,100],'tickwidth':1},
                       'bar':{'color':'#2563EB','thickness':0.2},
                       'steps':[{'range':[0,25],'color':'#FEE2E2'},{'range':[25,55],'color':'#FEF3C7'},
                                {'range':[55,100],'color':'#D1FAE5'}],
                       'threshold':{'line':{'color':'#EF4444','width':2},'value':50}}))
            fig.update_layout(height=280, margin=dict(l=20,r=20,t=40,b=10))
            st.plotly_chart(fig, use_container_width=True)

            delta = prob - base
            color = '#10B981' if delta > 0 else '#EF4444'
            st.markdown(f"""<div class="insight-box {'success' if delta > 0 else 'warn'}">
            vs 整体均值 <b>{base*100:.1f}%</b>, 偏差 <b style="color:{color}">{delta*100:+.1f}pp</b>
            </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_right:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("📊 转化驱动因素分析")
        # Real feature importance from data
        corr_data = df[['客户年龄','试驾时长','跟进总次数','平均沟通时长','跟进强度','首次跟进间隔天数']].copy()
        corr_data['转化'] = df['是否下订']
        cors = corr_data.corr()['转化'].drop('转化').abs().sort_values(ascending=True)
        fig = go.Figure(go.Bar(x=cors.values*100, y=cors.index, orientation='h',
                     text=[f'{v:.1f}%' for v in cors.values*100], textposition='outside',
                     marker_color='#2563EB'))
        fig.update_layout(height=300, xaxis_title="与转化的相关系数 (%)", margin=dict(l=10,r=60,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Dual charts
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.subheader("试驾时长 vs 转化")
            df['时长方块'] = pd.cut(df['试驾时长'], bins=[0,15,25,35,45,100],
                                    labels=['<15','15-25','25-35','35-45','45+'])
            td_cvr = df.groupby('时长方块')['是否下订'].mean() * 100
            fig = go.Figure(go.Bar(x=td_cvr.index, y=td_cvr.values, marker_color='#10B981',
                         text=[f'{v:.1f}%' for v in td_cvr.values], textposition='outside'))
            fig.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10), yaxis_title='转化率%')
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="chart-container">', unsafe_allow_html=True)
            st.subheader("跟进次数 vs 转化")
            df['跟进方块'] = pd.cut(df['跟进总次数'].fillna(0), bins=[-1,0,1,2,4,100],
                                   labels=['0','1','2','3-4','5+'])
            fu_cvr = df.groupby('跟进方块')['是否下订'].mean() * 100
            fig = go.Figure(go.Bar(x=fu_cvr.index, y=fu_cvr.values, marker_color='#F97316',
                         text=[f'{v:.1f}%' for v in fu_cvr.values], textposition='outside'))
            fig.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10), yaxis_title='转化率%')
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

# ===== TAB 4: 风险预警 =====
def render_risk(df):
    st.markdown('<p class="main-header">风险预警中心</p>', unsafe_allow_html=True)

    orders = df[df['订单ID'].notna()].copy()
    orders['风险分'] = 0
    if '售后平均满意度' in orders.columns:
        orders.loc[orders['售后平均满意度'] < 3.5, '风险分'] += 2
        orders.loc[orders['售后平均满意度'] < 2.5, '风险分'] += 3
    if '是否有投诉' in orders.columns:
        orders.loc[orders['是否有投诉'] == 1, '风险分'] += 3
    if '投诉次数' in orders.columns:
        orders.loc[orders['投诉次数'] >= 2, '风险分'] += 2
    orders['风险等级'] = pd.cut(orders['风险分'], bins=[-1,2,5,100], labels=['低风险','中风险','高风险'])

    # KPI row
    risk_counts = orders['风险等级'].value_counts()
    high = risk_counts.get('高风险', 0)
    mid = risk_counts.get('中风险', 0)
    low = risk_counts.get('低风险', 0)
    total_o = len(orders)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🔴 高风险", high, delta=f"{high/total_o*100:.1f}%",
                 delta_color="inverse" if high/total_o > 0.2 else "normal")
    with c2:
        st.metric("🟡 中风险", mid, delta=f"{mid/total_o*100:.1f}%",
                 delta_color="inverse" if mid/total_o > 0.3 else "normal")
    with c3:
        st.metric("🟢 低风险", low, delta=f"{low/total_o*100:.1f}%")
    with c4:
        avg_risk = orders['风险分'].mean()
        st.metric("📊 平均风险分", f"{avg_risk:.1f}", delta=f"满分10")

    st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("风险等级分布")
        fig = px.pie(values=[low, mid, high], names=['低风险','中风险','高风险'], hole=0.55,
                     color_discrete_sequence=['#10B981','#F59E0B','#EF4444'], height=350)
        fig.update_layout(margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("城市风险热力图")
        risk_pivot = orders.pivot_table(values='风险分', index='城市', columns='渠道', aggfunc='mean').fillna(0)
        fig = px.imshow(risk_pivot, text_auto='.1f', aspect='auto', color_continuous_scale='RdYlGn_r',
                        height=350, range_color=[0, 8])
        fig.update_layout(margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Complaint analysis
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.subheader("投诉分析")
    c1, c2, c3 = st.columns(3)
    with c1:
        if '主要投诉类型' in orders.columns:
            comp_type = orders['主要投诉类型'].value_counts().head(5)
            fig = px.bar(x=comp_type.index, y=comp_type.values, color=comp_type.index,
                        color_discrete_sequence=px.colors.qualitative.Bold, height=280)
            fig.update_layout(showlegend=False, yaxis_title='投诉量', xaxis_title='',
                              margin=dict(l=10,r=10,t=20,b=10))
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        if '主要投诉类型' in orders.columns and '售后平均满意度' in orders.columns:
            comp_sat = orders.groupby('主要投诉类型')['售后平均满意度'].mean().sort_values().head(5)
            fig = px.bar(x=comp_sat.index, y=comp_sat.values, color=comp_sat.index,
                        color_discrete_sequence=px.colors.qualitative.Pastel, height=280)
            fig.update_layout(showlegend=False, yaxis_title='平均满意度', xaxis_title='',
                              margin=dict(l=10,r=10,t=20,b=10))
            st.plotly_chart(fig, use_container_width=True)
    with c3:
        if '处理时长(天)' in orders.columns or '平均处理时长' in orders.columns:
            proc_col = '平均处理时长' if '平均处理时长' in orders.columns else '处理时长(天)'
            proc_time = orders.groupby('城市')[proc_col].mean().sort_values()
            fig = px.bar(x=proc_time.index, y=proc_time.values, color=proc_time.index,
                        color_discrete_sequence=px.colors.qualitative.Set3, height=280)
            fig.update_layout(showlegend=False, yaxis_title='平均处理天', xaxis_title='',
                              margin=dict(l=10,r=10,t=20,b=10))
            st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # High risk table
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.subheader("高风险客户明细")
    display_cols = ['线索ID','城市','渠道','交付评分','售后平均满意度','投诉次数','风险分']
    available = [c for c in display_cols if c in orders.columns]
    hr = orders[orders['风险等级']=='高风险'][available].sort_values('风险分', ascending=False).head(30)
    st.dataframe(hr, use_container_width=True, hide_index=True)
    csv = hr.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 导出高风险客户CSV", csv, "high_risk_customers.csv", "text/csv")
    st.markdown('</div>', unsafe_allow_html=True)

# ===== TAB 5: 销售员分析 =====
def render_salesperson(df):
    st.markdown('<p class="main-header">销售团队绩效</p>', unsafe_allow_html=True)

    sp_data = df[df['跟进总次数'] > 0]
    if '主要销售员ID' not in sp_data.columns:
        st.info("销售员信息未关联到宽表")
        return

    sp_stats = sp_data.groupby('主要销售员ID').agg(
        处理线索=('线索ID','count'), 转化率=('是否下订','mean'), 订单量=('是否下订','sum'),
        平均沟通=('平均沟通时长','mean'), 面谈率=('面谈占比','mean')
    ).sort_values('转化率', ascending=False).reset_index()

    # Add rank info
    if '主要销售员职级' in sp_data.columns:
        ranks = sp_data.groupby('主要销售员ID')['主要销售员职级'].first()
        sp_stats['职级'] = sp_stats['主要销售员ID'].map(ranks)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("Top 15 销售员转化率")
        top15 = sp_stats.head(15).sort_values('转化率')
        fig = go.Figure(go.Bar(x=top15['转化率']*100, y=top15['主要销售员ID'], orientation='h',
                     text=[f'{v*100:.1f}%' for v in top15['转化率']], textposition='outside',
                     marker_color='#10B981'))
        fig.update_layout(height=420, margin=dict(l=10,r=50,t=10,b=10), yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("转化率 vs 处理量 散点")
        fig = px.scatter(sp_stats, x='处理线索', y='转化率', size='订单量', color='职级' if '职级' in sp_stats.columns else None,
                         hover_data=['主要销售员ID'], height=420, color_discrete_sequence=px.colors.qualitative.Bold)
        fig.update_layout(margin=dict(l=10,r=10,t=10,b=10))
        fig.update_yaxes(tickformat=',.0%')
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Summary stats
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("销售员数", len(sp_stats))
    with c2: st.metric("人均处理线索", f"{sp_stats['处理线索'].mean():.0f}")
    with c3: st.metric("最高转化率", f"{sp_stats['转化率'].max()*100:.1f}%")
    with c4: st.metric("人均订单", f"{sp_stats['订单量'].mean():.1f}")

# ===== TAB 6: 策略推荐 =====
def render_strategy(df, strategy_df):
    st.markdown('<p class="main-header">策略优化中心</p>', unsafe_allow_html=True)

    if strategy_df is not None and len(strategy_df) > 0:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.subheader("多场景策略评估")
        show_cols = ['Scenario','TOPSIS_Score','Total_Orders','Weighted_CVR','Coverage(%)']
        available = [c for c in show_cols if c in strategy_df.columns]
        scored = strategy_df[available].sort_values('TOPSIS_Score', ascending=False)

        c1, c2 = st.columns([1, 1])
        with c1:
            fig = go.Figure(go.Bar(x=scored['TOPSIS_Score'], y=scored['Scenario'], orientation='h',
                         text=[f'{v:.3f}' for v in scored['TOPSIS_Score']], textposition='outside',
                         marker_color='#2563EB'))
            fig.update_layout(height=300, margin=dict(l=10,r=60,t=10,b=10), xaxis_title='TOPSIS得分')
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.dataframe(scored.set_index('Scenario'), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Strategy cards
    st.subheader("四大核心策略")
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("💎 策略1: 预算重新分配", expanded=True):
            st.markdown("""
            | 动作 | 详情 |
            |------|------|
            | 削减 | 低ROI渠道(车展等)预算减20-30% |
            | 增加 | 懂车帝、抖音渠道预算增25-40% |
            | 预期 | 订单量 **+10-15%**，单客成本 **-8%** |
            | 风险 | 渠道依赖风险，建议分步实施 |
            """)
        with st.expander("🤝 策略2: 跟进流程优化", expanded=True):
            st.markdown("""
            | 动作 | 详情 |
            |------|------|
            | 方法 | 推广面谈跟进(因果效应+4pp) |
            | 时效 | 首次跟进≤3天 |
            | 时长 | 每次沟通15-25分钟为最优区间 |
            | 预期 | 转化率 **+3-5pp** |
            """)
    with c2:
        with st.expander("💰 策略3: 定价竞争应对", expanded=True):
            st.markdown("""
            | 场景 | 应对策略 |
            |------|---------|
            | 竞品降5% | **不跟降**，强化产品力 |
            | 竞品降10% | **跟降5%**，保份额 |
            | 竞品降15%+ | 组合促销+服务升级 |
            """)
        with st.expander("🛡️ 策略4: 售后预警体系", expanded=True):
            st.markdown("""
            | 动作 | 详情 |
            |------|------|
            | 预警 | 交付评分<3自动标记 |
            | 响应 | 投诉24h内首次响应 |
            | 回访 | 高价值客户月度回访 |
            | 预期 | 流失率 **-20%**，满意度 **+0.5** |
            """)


# ===== MAIN =====
def main():
    # Password gate
    if not check_password():
        st.stop()

    st.markdown('<p style="font-size:2rem;font-weight:900;margin-bottom:0;">G9 智能销售运营决策系统</p>', unsafe_allow_html=True)
    st.caption("全链路数据驱动 | 因果推断 | 预测预警 | 策略优化 | Q4销量+15%")

    df = load_data()
    strategy_df = load_strategy()

    if df is None:
        st.error("未找到数据文件。请先运行 W1 数据清洗: `PYTHONIOENCODING=utf-8 python src/w1_cleaning.py`")
        return

    date_range, cities, channels, age_range, genders = render_sidebar(df)
    filtered = apply_filters(df, date_range, cities, channels, age_range, genders)

    tabs = st.tabs([
        "📊 运营全景", "📡 渠道分析", "🤖 预测中心",
        "⚠️ 风险预警", "👥 销售团队", "📋 策略推荐"
    ])

    with tabs[0]: render_overview(filtered)
    with tabs[1]: render_channels(filtered)
    with tabs[2]: render_prediction(filtered)
    with tabs[3]: render_risk(filtered)
    with tabs[4]: render_salesperson(filtered)
    with tabs[5]: render_strategy(filtered, strategy_df)

    st.markdown("---")
    st.caption("G9 智能销售运营决策系统 v2.0 | 数据仅本地处理 | 不外传")

if __name__ == '__main__':
    main()
