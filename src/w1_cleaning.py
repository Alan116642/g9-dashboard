"""
W1：数据清洗与数仓建设
- 读取6张Sheet
- 缺失值多策略处理
- 异常值多方法融合检测
- 多表关联构建宽表
- 衍生特征工程
- 数据质量报告 + 22张可视化图表
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.gridspec import GridSpec
from config import *
from utils import *

# ═══════════════════════════════════════════════════════════════
# 1. 数据读取
# ═══════════════════════════════════════════════════════════════

def load_all_sheets():
    """读取Excel中所有6张Sheet"""
    print('📖 读取数据文件...')
    xls = pd.ExcelFile(EXCEL_PATH)
    print(f'  发现 {len(xls.sheet_names)} 张Sheet: {xls.sheet_names}')

    dfs = {}
    sheet_map = {
        '销售线索': 'leads',
        '跟进日志': 'followup',
        '交付记录': 'delivery',
        '售后工单': 'aftersales',
        '销售员信息': 'salesperson',
        '门店成本': 'store_cost'
    }

    for sheet_name, key in sheet_map.items():
        dfs[key] = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
        print(f'  ✓ {sheet_name}: {dfs[key].shape[0]:,}行 × {dfs[key].shape[1]}列')

    return dfs

# ═══════════════════════════════════════════════════════════════
# 2. 缺失值处理
# ═══════════════════════════════════════════════════════════════

def analyze_missing(dfs):
    """分析各表缺失情况"""
    print('\n🔍 缺失值分析...')
    results = {}
    for name, df in dfs.items():
        missing = df.isnull().sum()
        missing = missing[missing > 0]
        if len(missing) > 0:
            print(f'  {name}:')
            for col, cnt in missing.items():
                pct = cnt / len(df) * 100
                results[f'{name}.{col}'] = {'count': cnt, 'pct': pct}
                print(f'    {col}: {cnt:,} ({pct:.1f}%)')
    return results

def handle_missing_values(dfs):
    """多策略处理缺失值"""
    print('\n🔧 处理缺失值...')

    # 跟进日志 - 沟通时长缺失（20%）
    fu = dfs['followup']
    missing_mask = fu['沟通时长(分钟)'].isnull()
    print(f'  跟进.沟通时长: {missing_mask.sum():,} 缺失 ({missing_mask.sum()/len(fu)*100:.1f}%)')

    # 策略: 按(销售员+跟进方式)分组中位数填充
    group_medians = fu.groupby(['销售员ID', '跟进方式'])['沟通时长(分钟)'].transform('median')
    # 对于无法分组的（某些组合可能全为NaN），用跟进方式的中位数
    method_medians = fu.groupby('跟进方式')['沟通时长(分钟)'].transform('median')
    # 最终用总体中位数兜底
    overall_median = fu['沟通时长(分钟)'].median()

    fu['沟通时长(分钟)_填充方法'] = '原始值'
    fu.loc[missing_mask & group_medians.notna(), '沟通时长(分钟)'] = group_medians[missing_mask & group_medians.notna()]
    fu.loc[missing_mask & group_medians.notna(), '沟通时长(分钟)_填充方法'] = '分组中位数'
    fu.loc[missing_mask & fu['沟通时长(分钟)'].isnull() & method_medians.notna(), '沟通时长(分钟)'] = method_medians[missing_mask & fu['沟通时长(分钟)'].isnull() & method_medians.notna()]
    fu.loc[missing_mask & fu['沟通时长(分钟)'].isnull() & method_medians.notna(), '沟通时长(分钟)_填充方法'] = '方式中位数'
    fu.loc[fu['沟通时长(分钟)'].isnull(), '沟通时长(分钟)'] = overall_median
    fu.loc[fu['沟通时长(分钟)'].isnull(), '沟通时长(分钟)_填充方法'] = '总体中位数'

    filled_methods = fu['沟通时长(分钟)_填充方法'].value_counts()
    print(f'  填充方式分布: {dict(filled_methods)}')

    dfs['followup'] = fu
    return dfs

# ═══════════════════════════════════════════════════════════════
# 3. 异常值检测
# ═══════════════════════════════════════════════════════════════

def detect_outliers_fusion(dfs):
    """多方法融合异常值检测"""
    print('\n🔍 异常值检测（IQR + Z-Score + 业务规则 融合）...')

    outlier_stats = {}

    # --- 试驾时长 ---
    leads = dfs['leads'].copy()
    col = '试驾时长'
    leads['outlier_iqr'] = outlier_iqr(leads[col])
    leads['outlier_zscore'] = outlier_zscore(leads[col])
    leads['outlier_business'] = (leads[col] < 2) | (leads[col] > 180)
    # 融合：至少2种方法标记
    leads['is_outlier'] = (leads[['outlier_iqr', 'outlier_zscore', 'outlier_business']].sum(axis=1) >= 2)
    n_out = leads['is_outlier'].sum()
    print(f'  试驾时长异常: {n_out} 条 ({n_out/len(leads)*100:.1f}%)')
    outlier_stats['试驾时长'] = n_out
    # 替换为中位数
    median_val = leads.loc[~leads['is_outlier'], col].median()
    leads.loc[leads['is_outlier'], col + '_raw'] = leads.loc[leads['is_outlier'], col]
    leads.loc[leads['is_outlier'], col] = median_val
    dfs['leads'] = leads

    # --- 交付里程 ---
    delivery = dfs['delivery'].copy()
    col = '交付里程'
    delivery['outlier_iqr'] = outlier_iqr(delivery[col])
    delivery['outlier_zscore'] = outlier_zscore(delivery[col])
    delivery['outlier_business'] = delivery[col] > 500
    delivery['is_outlier'] = (delivery[['outlier_iqr', 'outlier_zscore', 'outlier_business']].sum(axis=1) >= 2)
    n_out = delivery['is_outlier'].sum()
    print(f'  交付里程异常: {n_out} 条 ({n_out/len(delivery)*100:.1f}%)')
    outlier_stats['交付里程'] = n_out
    median_val = delivery.loc[~delivery['is_outlier'], col].median()
    delivery.loc[delivery['is_outlier'], col + '_raw'] = delivery.loc[delivery['is_outlier'], col]
    delivery.loc[delivery['is_outlier'], col] = median_val
    dfs['delivery'] = delivery

    # --- 售后处理时长 ---
    aftersales = dfs['aftersales'].copy()
    col = '处理时长(天)'
    aftersales['outlier_business'] = aftersales[col] > 45
    n_out = aftersales['outlier_business'].sum()
    print(f'  处理时长极端值(>45天): {n_out} 条 ({n_out/len(aftersales)*100:.1f}%)')
    outlier_stats['处理时长(>45天)'] = n_out
    dfs['aftersales'] = aftersales

    return dfs, outlier_stats

# ═══════════════════════════════════════════════════════════════
# 4. 聚合函数
# ═══════════════════════════════════════════════════════════════

def build_wide_table(dfs):
    """多表关联构建统一宽表"""
    print('\n🔗 构建宽表（多表关联）...')

    leads = dfs['leads'].copy()
    followup = dfs['followup'].copy()
    delivery = dfs['delivery'].copy()
    aftersales = dfs['aftersales'].copy()
    salesperson = dfs['salesperson'].copy()
    store_cost = dfs['store_cost'].copy()

    # === 左连接1: 跟进日志聚合 ===
    print('  1/5 聚合跟进日志...')
    # 添加月份列用于后续匹配
    leads['线索月份'] = pd.to_datetime(leads['日期']).dt.to_period('M').astype(str)

    fu_agg = followup.groupby('线索ID').agg(
        跟进总次数=('跟进ID', 'count'),
        平均沟通时长=('沟通时长(分钟)', 'mean'),
        最大沟通时长=('沟通时长(分钟)', 'max'),
        沟通时长标准差=('沟通时长(分钟)', 'std'),
        最早跟进日期=('跟进日期', 'min'),
        最晚跟进日期=('跟进日期', 'max'),
        主要跟进方式=('跟进方式', mode_or_first),
        电话占比=('跟进方式', lambda x: (x == '电话').mean()),
        微信占比=('跟进方式', lambda x: (x == '微信').mean()),
        面谈占比=('跟进方式', lambda x: (x == '面谈').mean()),
        主要销售员ID=('销售员ID', mode_or_first),
        涉及销售员数=('销售员ID', 'nunique'),
    ).reset_index()

    # 合并跟进特征
    wide = leads.merge(fu_agg, on='线索ID', how='left')
    # 未跟进的线索填充默认值
    no_fu_mask = wide['跟进总次数'].isnull()
    wide.loc[no_fu_mask, '跟进总次数'] = 0
    wide.loc[no_fu_mask, '平均沟通时长'] = 0
    wide.loc[no_fu_mask, '最大沟通时长'] = 0
    wide.loc[no_fu_mask, '电话占比'] = 0
    wide.loc[no_fu_mask, '微信占比'] = 0
    wide.loc[no_fu_mask, '面谈占比'] = 0
    wide.loc[no_fu_mask, '涉及销售员数'] = 0
    print(f'    跟进聚合: {len(fu_agg)} -> {len(wide)} 行 (左连接)')

    # 跟进时间衍生
    wide['线索日期_dt'] = pd.to_datetime(wide['日期'])
    wide['最早跟进日期_dt'] = pd.to_datetime(wide['最早跟进日期'])
    wide['最晚跟进日期_dt'] = pd.to_datetime(wide['最晚跟进日期'])
    wide['首次跟进间隔天数'] = (wide['最早跟进日期_dt'] - wide['线索日期_dt']).dt.days
    wide['跟进天数跨度'] = (wide['最晚跟进日期_dt'] - wide['最早跟进日期_dt']).dt.days
    wide['跟进强度'] = wide['跟进总次数'] / (wide['跟进天数跨度'] + 1)
    wide.loc[no_fu_mask, '首次跟进间隔天数'] = -1
    wide.loc[no_fu_mask, '跟进天数跨度'] = 0
    wide.loc[no_fu_mask, '跟进强度'] = 0
    wide['沟通时长标准差'] = wide['沟通时长标准差'].fillna(0)

    # === 左连接2: 交付记录（先去重，确保1:1） ===
    print('  2/5 合并交付记录...')
    delivery_cols = ['线索ID', '订单ID', '交付日期', '车型', '配置', '颜色',
                     '交付里程', '是否延迟交付', '交付评分']
    delivery_dedup = delivery[delivery_cols].drop_duplicates(subset=['线索ID'], keep='first')
    wide = wide.merge(delivery_dedup, on='线索ID', how='left')
    wide['线索到交付天数'] = (pd.to_datetime(wide['交付日期']) - wide['线索日期_dt']).dt.days
    print(f'    交付记录: {len(delivery_dedup)} -> {len(wide)} 行 (左连接)')
    # Recalculate no_fu_mask after merge
    no_fu_mask = wide['跟进总次数'].isnull() | (wide['跟进总次数'] == 0)

    # === 左连接3: 售后工单聚合 ===
    print('  3/5 聚合售后工单...')
    as_agg = aftersales.groupby('订单ID').agg(
        投诉次数=('工单ID', 'count'),
        主要投诉类型=('投诉类型', mode_or_first),
        投诉类型数=('投诉类型', 'nunique'),
        平均处理时长=('处理时长(天)', 'mean'),
        最大处理时长=('处理时长(天)', 'max'),
        售后平均满意度=('满意度评分', 'mean'),
        售后最低满意度=('满意度评分', 'min'),
    ).reset_index()

    wide = wide.merge(as_agg, on='订单ID', how='left')
    wide['是否有投诉'] = wide['投诉次数'].notna().astype(int)
    wide['投诉次数'] = wide['投诉次数'].fillna(0).astype(int)
    wide['投诉类型数'] = wide['投诉类型数'].fillna(0).astype(int)
    wide['平均处理时长'] = wide['平均处理时长'].fillna(0)
    wide['最大处理时长'] = wide['最大处理时长'].fillna(0)
    wide['售后平均满意度'] = wide['售后平均满意度'].fillna(0)
    wide['售后最低满意度'] = wide['售后最低满意度'].fillna(0)
    print(f'    售后聚合: {len(as_agg)} 订单 -> {len(wide)} 行')

    # === 左连接4: 销售员信息 ===
    print('  4/5 合并销售员信息...')
    sp_cols = ['销售员ID', '城市', '职级', '入职日期', '绩效评级']
    sp_renamed = salesperson[sp_cols].rename(columns={
        '城市': '销售员城市',
        '职级': '主要销售员职级',
        '入职日期': '销售员入职日期',
        '绩效评级': '主要销售员绩效'
    })
    wide = wide.merge(sp_renamed, left_on='主要销售员ID', right_on='销售员ID', how='left')
    wide['销售员经验天数'] = (wide['线索日期_dt'] - pd.to_datetime(wide['销售员入职日期'])).dt.days
    wide.loc[no_fu_mask, '销售员经验天数'] = -1
    wide.loc[no_fu_mask, '主要销售员职级'] = '无跟进'
    wide.loc[no_fu_mask, '主要销售员绩效'] = '无跟进'
    print(f'    销售员: {len(sp_renamed)} 人')

    # === 左连接5: 门店成本 ===
    print('  5/5 合并门店成本...')
    wide = wide.merge(store_cost, left_on=['城市', '线索月份'],
                      right_on=['城市', '月份'], how='left')
    wide['总运营成本万'] = wide['租金(万)'] + wide['水电(万)'] + wide['市场费用(万)']
    print(f'    门店成本: {len(store_cost)} 条')

    # === 衍生特征 ===
    print('\n🧮 计算衍生特征...')
    # 客户年龄分段
    wide['年龄分段'] = pd.cut(wide['客户年龄'], bins=[0, 25, 35, 45, 55, 100],
                            labels=['18-25', '26-35', '36-45', '46-55', '56+'])
    # 时间特征
    wide['线索月份_num'] = wide['线索日期_dt'].dt.month
    wide['线索星期'] = wide['线索日期_dt'].dt.dayofweek
    wide['是否周末'] = (wide['线索星期'] >= 5).astype(int)
    wide['季度'] = wide['线索日期_dt'].dt.quarter.map({3: 'Q3', 4: 'Q4'})

    # 城市竞争强度（同城市同月的线索数）
    city_month_counts = wide.groupby(['城市', '线索月份']).size().reset_index(name='城市当月线索数')
    wide = wide.merge(city_month_counts, on=['城市', '线索月份'], how='left')

    # 渠道历史转化率
    channel_cvr = wide.groupby('渠道')['是否下订'].mean().to_dict()
    wide['渠道历史转化率'] = wide['渠道'].map(channel_cvr)

    # 销售员近期转化率（简化：用整体转化率作为代理）
    sp_cvr = wide[wide['是否下订'].notna()].groupby('主要销售员ID')['是否下订'].mean().to_dict()
    wide['销售员历史转化率'] = wide['主要销售员ID'].map(sp_cvr).fillna(wide['是否下订'].mean())

    # === 清理临时列 ===
    drop_cols = ['线索日期_dt', '最早跟进日期_dt', '最晚跟进日期_dt',
                 '线索月份_num', '线索星期', '月份',
                 'outlier_iqr', 'outlier_zscore', 'outlier_business']
    existing_drops = [c for c in drop_cols if c in wide.columns]
    wide = wide.drop(columns=existing_drops)

    print(f'\n✅ 宽表构建完成: {wide.shape[0]:,} 行 × {wide.shape[1]} 列')
    print(f'   - 成交线索: {wide["是否下订"].sum():,} ({wide["是否下订"].mean()*100:.1f}%)')
    print(f'   - 有跟进: {(wide["跟进总次数"] > 0).sum():,}')
    print(f'   - 有订单: {wide["订单ID"].notna().sum():,}')
    print(f'   - 有投诉: {wide["是否有投诉"].sum():,}')

    return wide

# ═══════════════════════════════════════════════════════════════
# 5. 数据质量报告
# ═══════════════════════════════════════════════════════════════

def generate_quality_report(dfs, wide, outlier_stats):
    """生成数据质量报告"""
    print('\n📋 生成数据质量报告...')

    lines = []
    lines.append('# G9 销售运营数据 — 数据质量报告 (W1)\n')
    lines.append(f'**生成日期**: {pd.Timestamp.now().strftime("%Y-%m-%d")}\n')

    lines.append('## 1. 数据概览\n')
    lines.append('| Sheet | 行数 | 列数 | 缺失列 |')
    lines.append('|-------|------|------|--------|')
    for name, df in dfs.items():
        missing_cols = df.isnull().sum()
        missing_cols = missing_cols[missing_cols > 0]
        mc = ', '.join([f'{c}({v})' for c, v in missing_cols.items()]) if len(missing_cols) > 0 else '无'
        lines.append(f'| {name} | {df.shape[0]:,} | {df.shape[1]} | {mc} |')

    lines.append(f'\n## 2. 宽表概览\n')
    lines.append(f'- **行数**: {wide.shape[0]:,}')
    lines.append(f'- **列数**: {wide.shape[1]}')
    lines.append(f'- **成交率**: {wide["是否下订"].mean()*100:.1f}%')
    lines.append(f'- **有跟进比例**: {(wide["跟进总次数"] > 0).mean()*100:.1f}%')
    lines.append(f'- **有订单比例**: {wide["订单ID"].notna().mean()*100:.1f}%')

    lines.append(f'\n## 3. 缺失值处理\n')
    lines.append('- 跟进日志.沟通时长: 6,666条缺失(20%) → 按(销售员+跟进方式)分组中位数填充')
    lines.append('- 未跟进线索: 跟进相关特征填充为0')
    lines.append('- 无投诉订单: 售后特征填充为0')

    lines.append(f'\n## 4. 异常值统计\n')
    for col, cnt in outlier_stats.items():
        lines.append(f'- {col}: {cnt} 条异常')

    lines.append(f'\n## 5. 衍生特征列表\n')
    for col in wide.columns:
        if col not in ['线索ID', '日期', '城市', '渠道', '客户年龄', '客户性别',
                        '试驾时长', '是否下订', '订单ID', '交付日期']:
            lines.append(f'- {col}')

    lines.append(f'\n## 6. 列统计摘要\n')
    lines.append('| 列名 | 类型 | 缺失 | 均值 | 中位数 | 最小值 | 最大值 |')
    lines.append('|------|------|------|------|--------|--------|--------|')
    for col in wide.columns[:50]:  # 前50列
        if wide[col].dtype in ['int64', 'float64']:
            lines.append(f'| {col} | {wide[col].dtype} | {wide[col].isnull().sum()} | '
                        f'{wide[col].mean():.2f} | {wide[col].median():.2f} | '
                        f'{wide[col].min():.2f} | {wide[col].max():.2f} |')

    report = '\n'.join(lines)
    path = os.path.join(REPORTS_DIR, 'W1_data_quality_report.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'  ✓ 报告已保存: {path}')
    return report

# ═══════════════════════════════════════════════════════════════
# 6. 可视化
# ═══════════════════════════════════════════════════════════════

def create_all_charts(wide, dfs, outlier_stats):
    """生成W1全部22张图表"""
    print('\n📊 生成W1可视化图表...')
    os.makedirs(os.path.join(REPORTS_DIR, 'W1_charts'), exist_ok=True)

    # 01: KPI 指标卡
    chart_01_kpi_cards(wide)

    # 02: 6表关系图
    chart_02_relational_diagram()

    # 03-04: 缺失值
    chart_03_missing_heatmap(dfs)
    chart_04_missing_bar(dfs)

    # 05-07: 异常值
    chart_05_testdrive_boxplot(wide)
    chart_06_mileage_boxplot(dfs['delivery'])
    chart_07_outlier_scatter(wide)

    # 08-09: 分布
    chart_08_age_distribution(wide)
    chart_09_testdrive_hist(wide)

    # 10-12: 分类对比
    chart_10_city_bar(wide)
    chart_11_channel_bar(wide)
    chart_12_gender_pie(wide)

    # 13: 配置×颜色
    chart_13_config_color_heatmap(dfs['delivery'])

    # 14-16: 时间序列
    chart_14_monthly_leads(wide)
    chart_15_monthly_conversion(wide)
    chart_16_daily_leads(wide)

    # 17-18: 相关性
    chart_17_correlation_heatmap(wide)
    chart_18_pairplot(wide)

    # 19-22: 业务分析
    chart_19_followup_intensity(wide)
    chart_20_comm_duration_violin(wide)
    chart_21_rank_conversion(wide)
    chart_22_store_cost(wide)

    print(f'\n✅ W1全部22张图表生成完成!')

# ---- 各图表函数 ----

def chart_01_kpi_cards(wide):
    fig, axes = plt.subplots(1, 6, figsize=(18, 3))
    kpis = [
        ('总线索', len(wide), '#2563EB', '条'),
        ('转化率', wide['是否下订'].mean()*100, '#10B981', '%'),
        ('总订单', wide['订单ID'].nunique(), '#F97316', '单'),
        ('延迟交付率', wide[wide['订单ID'].notna()]['是否延迟交付'].mean()*100, '#EF4444', '%'),
        ('交付评分', wide[wide['交付评分'].notna()]['交付评分'].mean(), '#8B5CF6', '分'),
        ('售后满意度', wide[wide['售后平均满意度'] > 0]['售后平均满意度'].mean(), '#06B6D4', '分'),
    ]
    for ax, (title, val, color, unit) in zip(axes, kpis):
        ax.text(0.5, 0.55, f'{val:.1f}' if val < 100 else f'{val:,.0f}',
                transform=ax.transAxes, fontsize=28, fontweight='bold', ha='center', color=color)
        ax.text(0.5, 0.2, f'{title}\n{unit}', transform=ax.transAxes, fontsize=11, ha='center', color='#6B7280')
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    fig.suptitle('G9 销售运营核心指标', fontsize=16, fontweight='bold', y=1.05)
    save_fig(fig, '01_kpi_cards.png', 'W1')

def chart_02_relational_diagram():
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlim(0, 14); ax.set_ylim(0, 8); ax.axis('off')
    boxes = {
        '销售线索\n15,000行': (3, 6), '跟进日志\n33,305行': (7, 6),
        '交付记录\n5,000行': (3, 3), '售后工单\n6,000行': (7, 3),
        '销售员信息\n50行': (11, 4.5), '门店成本\n60行': (3, 0.5)
    }
    for text, (x, y) in boxes.items():
        ax.add_patch(plt.Rectangle((x-1.5, y-0.5), 3, 1, fill=True, facecolor='#EFF6FF', edgecolor='#2563EB', lw=2))
        ax.text(x, y, text, ha='center', va='center', fontsize=10, fontweight='bold')
    arrows = [
        (4.5, 5.8, 5.5, 5.8, '线索ID (1:M)'),
        (3, 3.5, 3, 5.5, '线索ID (1:1)'),
        (4.5, 3, 5.5, 3, '订单ID (1:M)'),
        (7, 5.5, 9.5, 5, '销售员ID'),
        (3, 5.5, 3, 1, '城市+月份'),
    ]
    for x1, y1, x2, y2, label in arrows:
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='->', color='#6B7280', lw=1.5))
        ax.text((x1+x2)/2, (y1+y2)/2+0.15, label, fontsize=8, ha='center', color='#6B7280')
    ax.set_title('数据关系模型（6表关联）', fontsize=14, fontweight='bold', pad=20)
    save_fig(fig, '02_relational_diagram.png', 'W1')

def chart_03_missing_heatmap(dfs):
    all_missing = pd.DataFrame({name: df.isnull().sum()/len(df)*100 for name, df in dfs.items()})
    all_missing = all_missing.loc[all_missing.sum(axis=1) > 0]
    if all_missing.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 3))
    sns.heatmap(all_missing.T, annot=True, fmt='.1f', cmap='Reds', ax=ax,
                cbar_kws={'label': '缺失比例 (%)'}, vmin=0, vmax=100)
    ax.set_title('各表缺失值热力图 (%)', fontsize=14, fontweight='bold')
    save_fig(fig, '03_missing_heatmap.png', 'W1')

def chart_04_missing_bar(dfs):
    missing_data = []
    for name, df in dfs.items():
        for col in df.columns:
            pct = df[col].isnull().sum()/len(df)*100
            if pct > 0:
                missing_data.append({'Table': name, 'Column': col, 'Missing%': pct})
    if not missing_data:
        return
    md = pd.DataFrame(missing_data).sort_values('Missing%', ascending=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.barh(range(len(md)), md['Missing%'], color='#EF4444', alpha=0.8)
    ax.set_yticks(range(len(md)))
    ax.set_yticklabels([f"{r['Table']}.{r['Column']}" for _, r in md.iterrows()], fontsize=9)
    ax.set_xlabel('缺失比例 (%)')
    ax.set_title('各列缺失比例', fontsize=14, fontweight='bold')
    for i, (_, r) in enumerate(md.iterrows()):
        ax.text(r['Missing%']+0.5, i, f'{r["Missing%"]:.1f}%', va='center', fontsize=8)
    save_fig(fig, '04_missing_bar.png', 'W1')

def chart_05_testdrive_boxplot(wide):
    fig, ax = plt.subplots(figsize=(14, 6))
    city_order = wide.groupby('城市')['试驾时长'].mean().sort_values().index
    bp = ax.boxplot([wide[wide['城市']==c]['试驾时长'] for c in city_order],
                    labels=city_order, patch_artist=True, showfliers=True, flierprops=dict(marker='o', alpha=0.4))
    for patch, city in zip(bp['boxes'], city_order):
        patch.set_facecolor(CITY_COLORS.get(city, '#6B7280'))
    ax.set_ylabel('试驾时长 (分钟)')
    ax.set_title('试驾时长箱线图 — 按城市分组', fontsize=14, fontweight='bold')
    ax.axhline(y=2, color='red', linestyle='--', alpha=0.5, label='异常下限(2min)')
    ax.axhline(y=180, color='red', linestyle='--', alpha=0.5, label='异常上限(180min)')
    ax.legend(fontsize=8)
    save_fig(fig, '05_testdrive_boxplot.png', 'W1')

def chart_06_mileage_boxplot(delivery):
    fig, ax = plt.subplots(figsize=(10, 5))
    configs = delivery['配置'].unique()
    bp = ax.boxplot([delivery[delivery['配置']==c]['交付里程'] for c in configs],
                    labels=configs, patch_artist=True)
    for patch, c in zip(bp['boxes'], configs):
        patch.set_facecolor(CATEGORICAL_10[list(configs).index(c)])
    ax.set_ylabel('交付里程 (km)')
    ax.set_title('交付里程箱线图 — 按配置分组', fontsize=14, fontweight='bold')
    ax.axhline(y=500, color='red', linestyle='--', alpha=0.5, label='异常阈值(500km)')
    ax.legend()
    save_fig(fig, '06_mileage_boxplot.png', 'W1')

def chart_07_outlier_scatter(wide):
    fig, ax = plt.subplots(figsize=(10, 6))
    has_outlier = wide['is_outlier'] if 'is_outlier' in wide.columns else pd.Series(False, index=wide.index)
    ax.scatter(wide.loc[~has_outlier, '试驾时长'], wide.loc[~has_outlier, '试驾时长'],
              alpha=0.3, s=5, c='#2563EB', label='正常')
    ax.scatter(wide.loc[has_outlier, '试驾时长'] if has_outlier.sum()>0 else [],
              wide.loc[has_outlier, '试驾时长'] if has_outlier.sum()>0 else [],
              alpha=0.7, s=20, c='#EF4444', label=f'异常({has_outlier.sum()}条)', zorder=5)
    ax.set_xlabel('试驾时长 (分钟)'); ax.set_ylabel('试驾时长 (分钟)')
    ax.set_title('异常值检测结果分布', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, '07_outlier_scatter.png', 'W1')

def chart_08_age_distribution(wide):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, gender, color in zip(axes, ['男', '女'], ['#2563EB', '#EC4899']):
        data = wide[wide['客户性别']==gender]['客户年龄']
        ax.hist(data, bins=30, alpha=0.7, color=color, edgecolor='white', density=True)
        data.plot.kde(ax=ax, color=color, lw=2, linestyle='--')
        ax.axvline(data.mean(), color='red', linestyle='--', lw=1, label=f'均值: {data.mean():.1f}')
        ax.set_title(f'{gender}性 ({len(data):,}人)', fontsize=12)
        ax.set_xlabel('年龄'); ax.legend()
    fig.suptitle('客户年龄分布', fontsize=14, fontweight='bold')
    save_fig(fig, '08_age_distribution.png', 'W1')

def chart_09_testdrive_hist(wide):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for ax, label, color in zip(axes, [0, 1], ['#6B7280', '#10B981']):
        data = wide[wide['是否下订']==label]['试驾时长']
        ax.hist(data, bins=30, alpha=0.7, color=color, edgecolor='white')
        ax.axvline(data.mean(), color='red', linestyle='--', lw=1, label=f'均值: {data.mean():.1f}')
        ax.set_title(f'{"已下订" if label else "未下订"} ({len(data):,})', fontsize=12)
        ax.set_xlabel('试驾时长 (分钟)'); ax.legend()
    fig.suptitle('试驾时长分布 — 按是否下订分层', fontsize=14, fontweight='bold')
    save_fig(fig, '09_testdrive_hist.png', 'W1')

def chart_10_city_bar(wide):
    fig, ax1 = plt.subplots(figsize=(14, 6))
    city_stats = wide.groupby('城市').agg(线索量=('线索ID', 'count'), 转化率=('是否下订', 'mean')).sort_values('线索量')
    bars = ax1.barh(range(len(city_stats)), city_stats['线索量'],
                    color=[CITY_COLORS.get(c, '#6B7280') for c in city_stats.index])
    ax1.set_yticks(range(len(city_stats)))
    ax1.set_yticklabels(city_stats.index)
    ax1.set_xlabel('线索量')
    ax2 = ax1.twiny()
    ax2.plot(city_stats['转化率']*100, range(len(city_stats)), 'o-', color='#EF4444', lw=2, markersize=8, zorder=5)
    ax2.set_xlabel('转化率 (%)', color='#EF4444')
    ax2.tick_params(axis='x', colors='#EF4444')
    for i, (_, r) in enumerate(city_stats.iterrows()):
        ax1.text(r['线索量']+30, i, f'{int(r["线索量"]):,}', va='center', fontsize=9)
        ax2.text(r['转化率']*100+0.3, i, f'{r["转化率"]*100:.1f}%', va='center', fontsize=9, color='#EF4444')
    ax1.set_title('各城市线索量与转化率', fontsize=14, fontweight='bold')
    save_fig(fig, '10_city_bar.png', 'W1')

def chart_11_channel_bar(wide):
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ch_stats = wide.groupby('渠道').agg(线索量=('线索ID', 'count'), 转化率=('是否下订', 'mean')).sort_values('线索量', ascending=False)
    x = range(len(ch_stats))
    ax1.bar(x, ch_stats['线索量'], color=[CHANNEL_COLORS.get(c, '#6B7280') for c in ch_stats.index], width=0.6)
    ax2 = ax1.twinx()
    ax2.plot(x, ch_stats['转化率']*100, 'D-', color='#EF4444', lw=2, markersize=10, zorder=5)
    ax1.set_xticks(x); ax1.set_xticklabels(ch_stats.index)
    ax1.set_ylabel('线索量'); ax2.set_ylabel('转化率 (%)', color='#EF4444')
    ax2.tick_params(axis='y', colors='#EF4444')
    for i, (_, r) in enumerate(ch_stats.iterrows()):
        ax1.text(i, r['线索量']+50, f'{int(r["线索量"]):,}', ha='center', fontsize=10)
        ax2.text(i, r['转化率']*100+0.3, f'{r["转化率"]*100:.1f}%', ha='center', fontsize=10, color='#EF4444', fontweight='bold')
    ax1.set_title('各渠道线索量与转化率', fontsize=14, fontweight='bold')
    save_fig(fig, '11_channel_bar.png', 'W1')

def chart_12_gender_pie(wide):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    gender_counts = wide['客户性别'].value_counts()
    colors = ['#2563EB', '#EC4899']
    wedges, texts, autotexts = ax1.pie(gender_counts.values, labels=gender_counts.index,
                                        autopct='%1.1f%%', colors=colors, explode=(0.02, 0.02))
    ax1.set_title('客户性别分布', fontsize=13, fontweight='bold')

    gender_cvr = wide.groupby('客户性别')['是否下订'].mean() * 100
    ax2.bar(gender_cvr.index, gender_cvr.values, color=colors, width=0.5)
    for i, v in enumerate(gender_cvr.values):
        ax2.text(i, v+0.5, f'{v:.1f}%', ha='center', fontsize=14, fontweight='bold')
    ax2.set_title('各性别转化率', fontsize=13, fontweight='bold')
    ax2.set_ylabel('转化率 (%)')
    save_fig(fig, '12_gender_pie.png', 'W1')

def chart_13_config_color_heatmap(delivery):
    fig, ax = plt.subplots(figsize=(10, 6))
    ct = pd.crosstab(delivery['配置'], delivery['颜色'])
    sns.heatmap(ct, annot=True, fmt='d', cmap='Blues', ax=ax, linewidths=0.5)
    ax.set_title('配置 × 颜色 订单分布', fontsize=14, fontweight='bold')
    ax.set_xlabel('颜色'); ax.set_ylabel('配置')
    save_fig(fig, '13_config_color_heatmap.png', 'W1')

def chart_14_monthly_leads(wide):
    fig, ax = plt.subplots(figsize=(14, 6))
    monthly = wide.groupby(['线索月份', '渠道']).size().unstack(fill_value=0)
    months_sorted = sorted(monthly.index.unique())
    monthly = monthly.loc[months_sorted]
    monthly.plot(kind='area', ax=ax, stacked=True, alpha=0.8,
                 color=[CHANNEL_COLORS.get(c, '#6B7280') for c in monthly.columns])
    ax.set_xlabel('月份'); ax.set_ylabel('线索量')
    ax.set_title('月度线索量趋势 — 按渠道堆叠', fontsize=14, fontweight='bold')
    ax.legend(title='渠道', bbox_to_anchor=(1.02, 1), fontsize=9)
    save_fig(fig, '14_monthly_leads.png', 'W1')

def chart_15_monthly_conversion(wide):
    fig, ax = plt.subplots(figsize=(14, 6))
    for city in ['北京','上海','广州','深圳','杭州','成都']:
        city_data = wide[wide['城市']==city]
        monthly = city_data.groupby('线索月份')['是否下订'].mean() * 100
        months_sorted = sorted(monthly.index.unique())
        monthly = monthly.loc[months_sorted]
        ax.plot(range(len(monthly)), monthly.values, 'o-', lw=2, label=city,
                color=CITY_COLORS.get(city, '#6B7280'), markersize=6)
    ax.set_xticks(range(len(months_sorted)))
    ax.set_xticklabels(months_sorted)
    ax.set_ylabel('转化率 (%)'); ax.set_xlabel('月份')
    ax.set_title('月度转化率趋势 — 主要城市对比', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    save_fig(fig, '15_monthly_conversion.png', 'W1')

def chart_16_daily_leads(wide):
    daily = wide.groupby('日期').size().reset_index(name='线索量')
    daily['日期'] = pd.to_datetime(daily['日期'])
    daily = daily.sort_values('日期')
    daily['7日MA'] = daily['线索量'].rolling(7).mean()
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.fill_between(range(len(daily)), daily['线索量'], alpha=0.3, color='#2563EB')
    ax.plot(range(len(daily)), daily['线索量'], lw=1, color='#2563EB', alpha=0.7, label='日线索量')
    ax.plot(range(len(daily)), daily['7日MA'], lw=2, color='#F97316', label='7日移动平均')
    ax.set_ylabel('线索量'); ax.set_title('每日线索量趋势', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, '16_daily_leads.png', 'W1')

def chart_17_correlation_heatmap(wide):
    num_cols = wide.select_dtypes(include=[np.number]).columns[:20]
    corr = wide[num_cols].corr()
    fig, ax = plt.subplots(figsize=(16, 12))
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, fmt='.2f', cmap='RdBu_r', center=0,
                ax=ax, linewidths=0.5, annot_kws={'fontsize': 8})
    ax.set_title('数值特征相关性热力图', fontsize=14, fontweight='bold')
    save_fig(fig, '17_correlation_heatmap.png', 'W1')

def chart_18_pairplot(wide):
    plot_cols = ['客户年龄', '试驾时长', '是否下订']
    if '交付评分' in wide.columns:
        plot_cols.append('交付评分')
    sample = wide[plot_cols].dropna().sample(min(500, len(wide)), random_state=SEED)
    g = sns.pairplot(sample, hue='是否下订', diag_kind='kde',
                     palette={0: '#6B7280', 1: '#10B981'}, plot_kws={'alpha': 0.5, 's': 15})
    g.fig.suptitle('关键特征散点矩阵', fontsize=14, fontweight='bold', y=1.02)
    save_fig(g.fig, '18_pairplot.png', 'W1')

def chart_19_followup_intensity(wide):
    fig, ax = plt.subplots(figsize=(10, 6))
    wide_fu = wide[wide['跟进总次数'] > 0].copy()
    wide_fu['强度分组'] = pd.cut(wide_fu['跟进强度'], bins=[0, 0.5, 1, 2, 5, 100],
                               labels=['0-0.5', '0.5-1', '1-2', '2-5', '5+'])
    stats = wide_fu.groupby('强度分组')['是否下订'].agg(['mean', 'count']).reset_index()
    stats['mean'] *= 100
    ax.bar(range(len(stats)), stats['mean'], color='#2563EB', alpha=0.8, width=0.6)
    ax.set_xticks(range(len(stats)))
    ax.set_xticklabels(stats['强度分组'])
    ax.set_xlabel('跟进强度分组'); ax.set_ylabel('转化率 (%)')
    ax.set_title('跟进强度 vs 转化率', fontsize=14, fontweight='bold')
    for i, r in stats.iterrows():
        ax.text(i, r['mean']+0.5, f'{r["mean"]:.1f}%\n(n={int(r["count"]):,})', ha='center', fontsize=9)
    save_fig(fig, '19_followup_intensity.png', 'W1')

def chart_20_comm_duration_violin(wide):
    fig, ax = plt.subplots(figsize=(12, 6))
    data = wide[wide['跟进总次数'] > 0]
    parts = ax.violinplot(
        [data[(data['主要跟进方式']==m) & (data['是否下订']==c)]['平均沟通时长']
         for m in ['电话', '微信', '面谈'] for c in [0, 1]],
        positions=[0.8, 1.2, 2.8, 3.2, 4.8, 5.2], showmeans=True
    )
    colors = ['#6B7280', '#10B981'] * 3
    for i, pc in enumerate(parts['bodies']):
        pc.set_facecolor(colors[i]); pc.set_alpha(0.7)
    ax.set_xticks([1, 3, 5]); ax.set_xticklabels(['电话', '微信', '面谈'])
    ax.set_ylabel('平均沟通时长 (分钟)')
    ax.set_xlabel('跟进方式')
    ax.set_title('沟通时长分布 — 跟进方式 × 成交', fontsize=14, fontweight='bold')
    # legend
    from matplotlib.patches import Patch
    ax.legend([Patch(facecolor='#10B981', alpha=0.7), Patch(facecolor='#6B7280', alpha=0.7)],
              ['已成交', '未成交'], fontsize=10)
    save_fig(fig, '20_comm_duration_violin.png', 'W1')

def chart_21_rank_conversion(wide):
    fig, ax = plt.subplots(figsize=(10, 5))
    ranks = ['初级', '中级', '高级', '资深']
    data = wide[wide['主要销售员职级'].isin(ranks)]
    stats = data.groupby('主要销售员职级')['是否下订'].agg(['mean', 'count', 'std']).reindex(ranks)
    stats['mean'] *= 100; stats['std'] *= 100
    bars = ax.bar(range(len(ranks)), stats['mean'], yerr=stats['std'],
                  color=[RANK_COLORS[r] for r in ranks], width=0.5, capsize=5, alpha=0.9)
    ax.set_xticks(range(len(ranks))); ax.set_xticklabels(ranks)
    ax.set_ylabel('转化率 (%)'); ax.set_xlabel('销售员职级')
    ax.set_title('销售员职级 vs 转化率 (含标准差)', fontsize=14, fontweight='bold')
    for i, (_, r) in enumerate(stats.iterrows()):
        ax.text(i, r['mean']+r['std']+0.5, f'{r["mean"]:.1f}%', ha='center', fontsize=11, fontweight='bold')
    save_fig(fig, '21_rank_conversion.png', 'W1')

def chart_22_store_cost(wide):
    fig, ax = plt.subplots(figsize=(14, 6))
    cost_data = wide.groupby('城市').agg(租金=('租金(万)', 'mean'), 水电=('水电(万)', 'mean'),
                                         市场费用=('市场费用(万)', 'mean')).sort_values('租金', ascending=False)
    cost_data.plot(kind='bar', stacked=True, ax=ax, color=['#2563EB', '#F59E0B', '#10B981'], width=0.7)
    ax.set_ylabel('万元/月'); ax.set_xlabel('')
    ax.set_title('各城市门店月均成本结构', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    for i, (_, r) in enumerate(cost_data.iterrows()):
        total = r['租金'] + r['水电'] + r['市场费用']
        ax.text(i, total+0.1, f'{total:.1f}万', ha='center', fontsize=9, fontweight='bold')
    save_fig(fig, '22_store_cost.png', 'W1')

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('  G9 W1: 数据清洗与数仓建设')
    print('=' * 60)

    # 1. 读取
    dfs = load_all_sheets()

    # 2. 缺失值
    analyze_missing(dfs)
    dfs = handle_missing_values(dfs)

    # 3. 异常值
    dfs, outlier_stats = detect_outliers_fusion(dfs)

    # 4. 宽表
    wide = build_wide_table(dfs)

    # 5. 保存
    print('\n💾 保存数据...')
    csv_path = os.path.join(DATA_DIR, 'wide_table.csv')
    wide.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'  ✓ wide_table.csv ({wide.shape[0]:,} x {wide.shape[1]})')

    # 6. 质量报告
    generate_quality_report(dfs, wide, outlier_stats)

    # 7. 可视化
    create_all_charts(wide, dfs, outlier_stats)

    print('\n🎉 W1 全部完成!')
    print(f'  宽表: {wide.shape[0]:,} 行 × {wide.shape[1]} 列')
    print(f'  图表: 22张 (reports/W1_charts/)')
    print(f'  报告: reports/W1_data_quality_report.md')
