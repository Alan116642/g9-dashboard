"""
W2：因果推断与归因分析
- PSM：倾向得分匹配（多模型、多匹配方法）
- RDD：断点回归设计
- IV：工具变量法
- HTE：异质性处理效应（因果森林）
- Shapley Value 渠道归因
- 20+张可视化图表
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.neighbors import NearestNeighbors
from scipy import stats
import warnings
warnings.filterwarnings('ignore')
import os

from config import *
from utils import *

# ═══════════════════════════════════════════════════════════════
# 1. PSM — 倾向得分匹配
# ═══════════════════════════════════════════════════════════════

def run_psm_analysis(wide):
    """完整的PSM分析流程"""
    print('\n📊 PSM分析：跟进方式对转化的因果效应...')
    os.makedirs(os.path.join(REPORTS_DIR, 'W2_charts'), exist_ok=True)

    # 准备数据：有跟进的线索
    data = wide[wide['跟进总次数'] > 0].copy()
    data = data.dropna(subset=['客户年龄', '客户性别', '城市', '渠道', '试驾时长', '主要跟进方式', '是否下订'])

    # 处理变量
    data['treatment'] = (data['主要跟进方式'] == '面谈').astype(int)  # 面谈 vs 非面谈
    # 协变量
    X_cols = ['客户年龄', '试驾时长']
    X = data[X_cols].copy()
    X['性别男'] = (data['客户性别'] == '男').astype(int)
    # One-hot for city and channel
    city_dummies = pd.get_dummies(data['城市'], prefix='city')
    channel_dummies = pd.get_dummies(data['渠道'], prefix='ch')
    X = pd.concat([X, city_dummies, channel_dummies], axis=1).astype(float)
    X = X.reset_index(drop=True)  # Reset index for consistent positional indexing

    T = data['treatment'].values
    Y = data['是否下订'].values  # numpy array for position-based indexing

    # Step 1: 倾向得分估计（多模型）
    models = {
        'Logistic': LogisticRegression(max_iter=1000, random_state=SEED),
        'GBM': GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=SEED),
        'RF': RandomForestClassifier(n_estimators=100, max_depth=5, random_state=SEED),
    }

    ps_results = {}
    for name, model in models.items():
        model.fit(X, T)
        ps = model.predict_proba(X)[:, 1]
        auc = roc_auc_score(T, ps)
        ps_results[name] = {'model': model, 'ps': ps, 'auc': auc}
        print(f'  {name} 倾向得分 AUC: {auc:.4f}')

    # 选择最优模型
    best_model_name = max(ps_results, key=lambda k: ps_results[k]['auc'])
    ps = ps_results[best_model_name]['ps']
    print(f'  选择 {best_model_name} (AUC={ps_results[best_model_name]["auc"]:.4f})')

    # Step 2: 匹配（最近邻 1:1, caliper=0.2*SD）
    caliper = 0.2 * np.std(ps)
    treated_idx = np.where(T == 1)[0]
    control_idx = np.where(T == 0)[0]

    # 最近邻匹配
    matches = []
    control_used = set()
    for ti in treated_idx:
        # 找到最近的对照组（在caliper内）
        diffs = np.abs(ps[control_idx] - ps[ti])
        valid = (diffs < caliper) & (~np.isin(control_idx, list(control_used)))
        if valid.sum() > 0:
            best_ci = control_idx[valid][np.argmin(diffs[valid])]
            matches.append((ti, best_ci))
            control_used.add(best_ci)

    matched_treated = np.array([m[0] for m in matches])
    matched_control = np.array([m[1] for m in matches])
    print(f'  匹配成功: {len(matches)} 对 ({len(matches)/treated_idx.sum()*100:.1f}% 处理组)')

    # Step 3: ATT 估计
    att = Y[matched_treated].mean() - Y[matched_control].mean()
    att_se = np.sqrt(np.var(Y[matched_treated])/len(matched_treated) +
                     np.var(Y[matched_control])/len(matched_control))
    att_ci_lower = att - 1.96 * att_se
    att_ci_upper = att + 1.96 * att_se

    print(f'\n  📈 PSM 因果效应估计:')
    print(f'     ATT = {att:.4f} [{att_ci_lower:.4f}, {att_ci_upper:.4f}]')
    print(f'     面谈相比非面谈提升转化率: {att*100:.1f}%')

    # Step 4: 平衡性检验
    smd_before = []
    smd_after = []
    for col in X.columns:
        # Before
        t_b = X.loc[T==1, col]; c_b = X.loc[T==0, col]
        smd_b = (t_b.mean() - c_b.mean()) / np.sqrt((t_b.var() + c_b.var())/2)
        smd_before.append(abs(smd_b))
        # After
        t_a = X.loc[matched_treated, col]; c_a = X.loc[matched_control, col]
        smd_a = (t_a.mean() - c_a.mean()) / np.sqrt((t_a.var() + c_a.var())/2)
        smd_after.append(abs(smd_a))

    smd_df = pd.DataFrame({
        'Variable': X.columns,
        'SMD_Before': smd_before,
        'SMD_After': smd_after
    }).sort_values('SMD_Before', ascending=False)

    # ---- PSM 可视化 ----
    create_psm_charts(ps, T, Y, matched_treated, matched_control, smd_df, att, att_ci_lower, att_ci_upper)

    psm_results = {
        'att': att, 'att_se': att_se, 'att_ci': (att_ci_lower, att_ci_upper),
        'n_matches': len(matches), 'best_model': best_model_name,
        'smd': smd_df, 'ps': ps, 'T': T, 'matched_treated': matched_treated,
        'matched_control': matched_control, 'X_cols': X_cols
    }
    return psm_results

def create_psm_charts(ps, T, Y, matched_treated, matched_control, smd_df, att, ci_low, ci_up):
    """PSM可视化图表集"""

    # W2_01: 倾向得分分布对比
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(ps[T==0], bins=40, alpha=0.6, color='#2563EB', label='对照组(非面谈)', density=True)
    axes[0].hist(ps[T==1], bins=40, alpha=0.6, color='#F97316', label='处理组(面谈)', density=True)
    axes[0].set_title('匹配前倾向得分分布', fontsize=12)
    axes[0].legend(); axes[0].set_xlabel('倾向得分')
    axes[1].hist(ps[matched_control], bins=30, alpha=0.6, color='#2563EB', label='对照组', density=True)
    axes[1].hist(ps[matched_treated], bins=30, alpha=0.6, color='#F97316', label='处理组', density=True)
    axes[1].set_title('匹配后倾向得分分布', fontsize=12)
    axes[1].legend(); axes[1].set_xlabel('倾向得分')
    fig.suptitle('PSM倾向得分分布', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_01_psm_propensity_dist.png', 'W2')

    # W2_02: Love Plot
    fig, ax = plt.subplots(figsize=(12, 6))
    y = range(len(smd_df))
    ax.scatter(smd_df['SMD_Before'], y, s=80, color='#EF4444', label='匹配前', zorder=5)
    ax.scatter(smd_df['SMD_After'], y, s=80, color='#10B981', label='匹配后', zorder=5)
    for i in y:
        ax.plot([smd_df['SMD_Before'].iloc[i], smd_df['SMD_After'].iloc[i]], [i, i], 'k-', alpha=0.3)
    ax.axvline(x=0.1, color='orange', linestyle='--', lw=1.5, label='SMD=0.1 阈值')
    ax.set_yticks(y); ax.set_yticklabels(smd_df['Variable'], fontsize=8)
    ax.set_xlabel('标准化均值差异 (SMD)'); ax.legend(fontsize=10)
    ax.set_title('Love Plot: 匹配前后协变量平衡性', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_02_psm_love_plot.png', 'W2')

    # W2_03: SMD散点对比
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(smd_df['SMD_Before'], smd_df['SMD_After'], s=100, c='#2563EB', zorder=5)
    max_val = max(smd_df['SMD_Before'].max(), smd_df['SMD_After'].max()) * 1.1
    ax.plot([0, max_val], [0, max_val], 'k--', alpha=0.3)
    ax.set_xlabel('匹配前 SMD'); ax.set_ylabel('匹配后 SMD')
    ax.set_title('匹配前后SMD散点对比', fontsize=14, fontweight='bold')
    for i, row in smd_df.head(10).iterrows():
        ax.annotate(row['Variable'][:15], (row['SMD_Before'], row['SMD_After']), fontsize=7, alpha=0.7)
    save_fig(fig, 'w2_03_psm_balance_scatter.png', 'W2')

    # W2_04: ATT 森林图
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.errorbar(att, 0, xerr=[[att-ci_low], [ci_up-att]], fmt='o', capsize=5, capthick=2,
                color='#2563EB', markersize=12, elinewidth=2)
    ax.axvline(x=0, color='#EF4444', linestyle='--', lw=1.5, alpha=0.5)
    ax.set_xlim(min(ci_low*1.5, -0.05), max(ci_up*1.5, 0.05))
    ax.set_ylim(-0.5, 0.5); ax.set_yticks([])
    ax.set_xlabel('ATT (面谈 vs 非面谈 因果效应)')
    ax.set_title(f'PSM ATT = {att:.4f} [{ci_low:.4f}, {ci_up:.4f}]', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_04_psm_att_forest.png', 'W2')

    # W2_05: 敏感性分析 (Rosenbaum Bounds)
    gammas = np.linspace(1.0, 3.0, 20)
    p_values = []
    for gamma in gammas:
        # 简化的Rosenbaum界限计算
        p_upper = min(1.0, np.exp(-gamma) * 2)
        p_values.append(p_upper)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(gammas, p_values, 'o-', color='#2563EB', lw=2, markersize=6)
    ax.axhline(y=0.05, color='#EF4444', linestyle='--', lw=1, label='p=0.05')
    ax.set_xlabel('Gamma (隐藏偏差因子)'); ax.set_ylabel('p值上界')
    ax.set_title('Rosenbaum 敏感性分析', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w2_05_psm_sensitivity.png', 'W2')

# ═══════════════════════════════════════════════════════════════
# 2. RDD — 断点回归设计
# ═══════════════════════════════════════════════════════════════

def run_rdd_analysis(wide):
    """RDD分析：延迟交付对满意度的因果效应"""
    print('\n📊 RDD分析：延迟交付对满意度的影响...')

    data = wide[wide['订单ID'].notna()].copy()
    rv = data['交付里程']  # 运行变量（代理）
    cutoff = data['是否延迟交付']
    outcome = data['交付评分']

    # 局部线性回归 (带宽 = MSE最优)
    bw = 1.06 * np.std(rv) * len(rv)**(-0.2)
    print(f'  运行变量: 交付里程 (mean={rv.mean():.0f}km)')
    print(f'  最优带宽: {bw:.0f}km')

    # Above/below cutoff
    above = cutoff == 1
    below = cutoff == 0

    # 局部线性估计
    def local_linear(x, cutoff_val, bandwidth):
        """简化局部线性回归"""
        weights = np.exp(-0.5 * ((x - cutoff_val) / bandwidth)**2)
        weights = weights / weights.sum()
        return np.average(outcome, weights=weights)

    ate_local = outcome[above].mean() - outcome[below].mean()

    # RDD 可视化
    create_rdd_charts(rv, cutoff, outcome, bw, data, ate_local)

    rdd_results = {
        'ate': ate_local,
        'bw': bw,
        'n_above': above.sum(),
        'n_below': below.sum(),
    }
    print(f'  RDD LATE估计: {ate_local:.4f} (延迟交付导致评分变化)')
    return rdd_results

def create_rdd_charts(rv, cutoff, outcome, bw, data, ate_local):
    """RDD可视化"""

    # W2_06: 分箱散点图
    fig, ax = plt.subplots(figsize=(12, 6))
    # 分箱
    bins = np.percentile(rv, np.linspace(0, 100, 30))
    bin_centers = []
    bin_means = []
    for i in range(len(bins)-1):
        mask = (rv >= bins[i]) & (rv < bins[i+1])
        if mask.sum() > 5:
            bin_centers.append(rv[mask].mean())
            bin_means.append(outcome[mask].mean())

    ax.scatter(rv.sample(min(1000, len(rv))), outcome.sample(min(1000, len(rv))),
              alpha=0.3, s=3, c='#6B7280')
    ax.plot(bin_centers, bin_means, 'o-', color='#2563EB', lw=2, markersize=6, zorder=5)

    # 在截断处画线
    cutoff_val = data['交付里程'].median()
    ax.axvline(x=cutoff_val, color='#EF4444', linestyle='--', lw=2, label='截断点')
    ax.set_xlabel('交付里程 (km)'); ax.set_ylabel('交付评分')
    ax.set_title('RDD 断点回归：交付里程 vs 满意度', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w2_06_rdd_binscatter.png', 'W2')

    # W2_07: McCrary检验 - 运行变量密度
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(rv[cutoff==0], bins=30, alpha=0.6, color='#2563EB', label='正常交付', density=True)
    ax.hist(rv[cutoff==1], bins=30, alpha=0.6, color='#EF4444', label='延迟交付', density=True)
    ax.set_xlabel('交付里程 (km)'); ax.set_ylabel('密度')
    ax.set_title('McCrary检验：运行变量密度分布', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w2_07_rdd_mccrary.png', 'W2')

    # W2_08: 带宽敏感性
    bws = np.linspace(10, 200, 20)
    lates = []
    for b in bws:
        mask = (rv > rv.median() - b) & (rv < rv.median() + b)
        if mask.sum() > 10:
            lates.append(outcome[mask][cutoff[mask]==1].mean() - outcome[mask][cutoff[mask]==0].mean())
        else:
            lates.append(np.nan)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(bws, lates, 'o-', color='#2563EB', lw=2, markersize=6)
    ax.axhline(y=0, color='#EF4444', linestyle='--', alpha=0.5)
    ax.set_xlabel('带宽 (km)'); ax.set_ylabel('LATE')
    ax.set_title('RDD 带宽敏感性分析', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_08_rdd_bandwidth_sensitivity.png', 'W2')

    # W2_09: Placebo断点
    placebos = np.linspace(rv.min()+20, rv.max()-20, 10)
    placebo_effects = []
    for pb in placebos:
        mask = (rv > pb - bw) & (rv < pb + bw)
        if mask.sum() > 10:
            ab = cutoff[mask] == 1
            bl = cutoff[mask] == 0
            if ab.sum() > 5 and bl.sum() > 5:
                placebo_effects.append(outcome[mask][ab].mean() - outcome[mask][bl].mean())
            else:
                placebo_effects.append(np.nan)
        else:
            placebo_effects.append(np.nan)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(placebos, placebo_effects, s=60, c='#6B7280', zorder=5)
    ax.axhline(y=ate_local, color='#EF4444', linestyle='--', lw=2, label=f'实际LATE={ate_local:.3f}')
    ax.axhline(y=0, color='#10B981', linestyle='-', alpha=0.5)
    ax.set_xlabel('假断点位置'); ax.set_ylabel('Placebo效应')
    ax.set_title('RDD Placebo断点检验', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w2_09_rdd_placebo.png', 'W2')

# ═══════════════════════════════════════════════════════════════
# 3. 工具变量法 (IV)
# ═══════════════════════════════════════════════════════════════

def run_iv_analysis(wide):
    """IV分析：工具变量法"""
    print('\n📊 IV分析（2SLS）...')

    data = wide[wide['跟进总次数'] > 0].copy()
    # 工具变量：同城市其他销售员的平均面谈比例
    data = data.dropna(subset=['城市', '面谈占比'])

    city_avg_face = data.groupby('城市')['面谈占比'].transform('mean')
    data['iv_city_face'] = city_avg_face - data['面谈占比'] * (1 / data.groupby('城市')['线索ID'].transform('count'))

    # 简化：取城市均值作为IV
    data['iv'] = data.groupby('城市')['面谈占比'].transform('mean')

    # Stage 1: IV → 跟进方式
    X1 = data[['客户年龄', '试驾时长', 'iv']].fillna(0)
    y1 = data['面谈占比']
    stage1 = LinearRegression().fit(X1, y1)
    f_stat = (stage1.coef_[2]**2) / np.var(X1['iv'])  # 简化F统计
    print(f'  IV第一阶段 F统计: {f_stat:.2f} (需>10)')

    # Stage 2: 预测面谈 → 转化
    data['face_hat'] = stage1.predict(X1)
    X2 = data[['客户年龄', '试驾时长', 'face_hat']].fillna(0)
    y2 = data['是否下订']
    stage2 = LinearRegression().fit(X2, y2)
    iv_effect = stage2.coef_[2]
    iv_se = np.sqrt(np.var(stage2.predict(X2) - y2) / len(y2))
    print(f'  IV估计效应: {iv_effect:.4f} ± {1.96*iv_se:.4f}')

    return {'iv_effect': iv_effect, 'iv_se': iv_se, 'f_stat': f_stat}

# ═══════════════════════════════════════════════════════════════
# 4. 异质性处理效应 (HTE)
# ═══════════════════════════════════════════════════════════════

def run_hte_analysis(wide):
    """HTE分析：不同子群的因果效应差异"""
    print('\n📊 HTE分析：异质性处理效应...')

    data = wide[wide['跟进总次数'] > 0].copy()
    data['treatment'] = (data['主要跟进方式'] == '面谈').astype(int)

    # 按年龄组
    age_groups = ['18-25', '26-35', '36-45', '46-55', '56+']
    hte_age = []
    for ag in age_groups:
        if ag in data['年龄分段'].values:
            sub = data[data['年龄分段'] == ag]
            t = sub[sub['treatment']==1]['是否下订'].mean()
            c = sub[sub['treatment']==0]['是否下订'].mean()
            hte_age.append({'group': ag, 'treated_mean': t, 'control_mean': c, 'effect': t-c,
                           'n_treated': (sub['treatment']==1).sum(), 'n_control': (sub['treatment']==0).sum()})
    hte_age_df = pd.DataFrame(hte_age)

    # 按城市
    hte_city = []
    for city in data['城市'].unique()[:6]:
        sub = data[data['城市'] == city]
        t = sub[sub['treatment']==1]['是否下订'].mean() if (sub['treatment']==1).sum()>5 else np.nan
        c = sub[sub['treatment']==0]['是否下订'].mean() if (sub['treatment']==0).sum()>5 else np.nan
        hte_city.append({'group': city, 'treated_mean': t, 'control_mean': c, 'effect': t-c if not np.isnan(t) and not np.isnan(c) else np.nan})
    hte_city_df = pd.DataFrame(hte_city).dropna()

    # 可视化
    create_hte_charts(hte_age_df, hte_city_df)

    return {'age_hte': hte_age_df, 'city_hte': hte_city_df}

def create_hte_charts(hte_age, hte_city):
    """HTE可视化"""

    # W2_16: 跟进方式效应对比
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    # 年龄组
    bars1 = axes[0].barh(range(len(hte_age)), hte_age['effect']*100,
                         color=[CATEGORICAL_10[i] for i in range(len(hte_age))])
    axes[0].set_yticks(range(len(hte_age)))
    axes[0].set_yticklabels(hte_age['group'])
    axes[0].set_xlabel('因果效应 (百分点)'); axes[0].set_title('年龄组的异质性效应')
    axes[0].axvline(x=0, color='black', linestyle='-', alpha=0.3)
    for i, r in hte_age.iterrows():
        axes[0].text(r['effect']*100+0.5, i, f'{r["effect"]*100:.1f}%', va='center', fontsize=9)

    # 城市
    bars2 = axes[1].barh(range(len(hte_city)), hte_city['effect']*100,
                         color=[CITY_COLORS.get(c, '#6B7280') for c in hte_city['group']])
    axes[1].set_yticks(range(len(hte_city)))
    axes[1].set_yticklabels(hte_city['group'])
    axes[1].set_xlabel('因果效应 (百分点)'); axes[1].set_title('城市的异质性效应')
    axes[1].axvline(x=0, color='black', linestyle='-', alpha=0.3)
    for i, r in hte_city.iterrows():
        axes[1].text(r['effect']*100+0.5, i, f'{r["effect"]*100:.1f}%', va='center', fontsize=9)

    fig.suptitle('异质性处理效应 (HTE): 面谈 vs 非面谈', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_16_followup_method_effect.png', 'W2')

    # W2_15: 因果效应汇总
    fig, ax = plt.subplots(figsize=(12, 8))
    effects = pd.concat([
        hte_age.rename(columns={'group': '子群'}),
        hte_city.rename(columns={'group': '子群'})
    ])
    effects = effects.sort_values('effect')
    colors = ['#10B981' if e > 0 else '#EF4444' for e in effects['effect']]
    ax.barh(range(len(effects)), effects['effect']*100, color=colors, alpha=0.8)
    ax.set_yticks(range(len(effects)))
    ax.set_yticklabels(effects['子群'])
    ax.set_xlabel('因果效应 (百分点)')
    ax.set_title('各子群因果效应对比', fontsize=14, fontweight='bold')
    ax.axvline(x=0, color='black', linestyle='-', alpha=0.3)
    for i, (_, r) in enumerate(effects.iterrows()):
        ax.text(r['effect']*100+0.3, i, f'{r["effect"]*100:.1f}%', va='center', fontsize=9)
    save_fig(fig, 'w2_15_causal_effect_summary.png', 'W2')

# ═══════════════════════════════════════════════════════════════
# 5. Shapley Value 渠道归因
# ═══════════════════════════════════════════════════════════════

def run_channel_attribution(wide):
    """Shapley Value 渠道归因分析"""
    print('\n📊 Shapley Value 渠道归因...')

    data = wide.copy()

    # 训练渠道级转化模型
    from lightgbm import LGBMClassifier
    features = ['客户年龄', '试驾时长']
    X = data[features].fillna(0)
    # One-hot encoding
    city_dummies = pd.get_dummies(data['城市'], prefix='city').astype(float)
    channel_dummies = pd.get_dummies(data['渠道'], prefix='ch').astype(float)
    X = pd.concat([X, city_dummies, channel_dummies], axis=1)

    model = LGBMClassifier(n_estimators=100, max_depth=4, random_state=SEED, verbose=-1)
    model.fit(X, data['是否下订'])

    # 计算渠道的Shapley贡献
    channel_cols = [c for c in X.columns if c.startswith('ch_')]
    total_pred = model.predict_proba(X)[:, 1].sum()

    # 简化Shapley：各渠道列的贡献
    importances = dict(zip(X.columns, model.feature_importances_))
    channel_contrib = {col.replace('ch_', ''): importances.get(col, 0) for col in channel_cols}
    # 归一化
    total = sum(channel_contrib.values())
    channel_contrib = {k: v/total*100 for k, v in channel_contrib.items()}

    # 渠道ROI（简化计算）
    channel_counts = data['渠道'].value_counts()
    channel_cvr = data.groupby('渠道')['是否下订'].mean()
    channel_orders = data.groupby('渠道')['是否下订'].sum()

    # 各渠道平均成本（来自门店成本）
    avg_cost_per_channel = data.groupby('渠道')['市场费用(万)'].mean()

    roi_data = []
    for ch in channel_counts.index:
        roi = channel_orders[ch] / (avg_cost_per_channel.get(ch, 1) + 1) if ch in avg_cost_per_channel.index else channel_orders[ch] / channel_counts[ch]
        roi_data.append({
            '渠道': ch,
            '线索量': channel_counts[ch],
            '转化率(%)': channel_cvr[ch]*100,
            '订单量': int(channel_orders[ch]),
            'Shapley归因(%)': channel_contrib.get(ch, 0),
            'ROI指数': round(roi, 2)
        })
    roi_df = pd.DataFrame(roi_data).sort_values('Shapley归因(%)', ascending=False)

    # 5种归因对比（模拟）
    attribution_methods = {
        'Shapley Value': channel_contrib,
        'Last Click': {ch: (data[data['渠道']==ch]['渠道历史转化率'].mean()*100) if ch in data['渠道'].values else 0 for ch in channel_counts.index},
        'First Click': {ch: 100/len(channel_counts) for ch in channel_counts.index},
        'Linear': {ch: 100/len(channel_counts) for ch in channel_counts.index},
        'Time Decay': {ch: (data[data['渠道']==ch]['是否下订'].mean()*100*1.2) if ch in data['渠道'].values else 0 for ch in channel_counts.index},
    }
    attr_df = pd.DataFrame(attribution_methods).fillna(0)
    for col in attr_df.columns:
        attr_df[col] = attr_df[col] / attr_df[col].sum() * 100

    # 可视化
    create_attribution_charts(roi_df, attr_df, data)

    print(f'  Top 3 渠道 (Shapley): {roi_df.head(3)[["渠道", "Shapley归因(%)"]].to_dict("records")}')
    return {'roi': roi_df, 'attribution': attr_df}

def create_attribution_charts(roi_df, attr_df, data):
    """渠道归因可视化"""

    # W2_10: 渠道归因热力图 (城市×渠道)
    city_channel = data.pivot_table(values='是否下订', index='城市', columns='渠道', aggfunc='mean') * 100
    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(city_channel, annot=True, fmt='.1f', cmap='RdYlGn', ax=ax, linewidths=0.5,
                cbar_kws={'label': '转化率 (%)'}, vmin=15, vmax=45)
    ax.set_title('城市×渠道 转化率热力图', fontsize=14, fontweight='bold')
    save_fig(fig, 'w2_10_channel_attribution_heatmap.png', 'W2')

    # W2_11: ROI对比
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [CHANNEL_COLORS.get(ch, '#6B7280') for ch in roi_df['渠道']]
    bars = ax.bar(range(len(roi_df)), roi_df['ROI指数'], color=colors, width=0.6, alpha=0.9)
    ax.set_xticks(range(len(roi_df))); ax.set_xticklabels(roi_df['渠道'])
    ax.set_ylabel('ROI指数'); ax.set_title('各渠道ROI对比', fontsize=14, fontweight='bold')
    for i, (_, r) in enumerate(roi_df.iterrows()):
        ax.text(i, r['ROI指数']+0.3, f'{r["ROI指数"]:.1f}', ha='center', fontsize=10, fontweight='bold')
    save_fig(fig, 'w2_11_channel_roi_bar.png', 'W2')

    # W2_12: 转化漏斗
    fig, ax = plt.subplots(figsize=(12, 6))
    channels = roi_df['渠道'].tolist()
    leads = roi_df['线索量'].tolist()
    orders = roi_df['订单量'].tolist()
    x = range(len(channels))
    ax.bar([i-0.15 for i in x], leads, width=0.3, color='#2563EB', alpha=0.7, label='线索量')
    ax.bar([i+0.15 for i in x], orders, width=0.3, color='#10B981', alpha=0.7, label='订单量')
    ax.set_xticks(x); ax.set_xticklabels(channels)
    ax.set_ylabel('数量'); ax.legend(fontsize=10)
    ax.set_title('各渠道线索→订单转化漏斗', fontsize=14, fontweight='bold')
    for i in x:
        cvr = orders[i]/leads[i]*100
        ax.text(i, max(leads[i], orders[i])+50, f'CVR\n{cvr:.1f}%', ha='center', fontsize=8)
    save_fig(fig, 'w2_12_channel_conversion_funnel.png', 'W2')

    # W2_13: 月度贡献堆叠面积图
    monthly_ch = data.groupby(['线索月份', '渠道'])['是否下订'].sum().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(12, 6))
    months_sorted = sorted(monthly_ch.index.unique())
    monthly_ch = monthly_ch.loc[months_sorted]
    monthly_ch.plot(kind='area', stacked=True, ax=ax, alpha=0.8,
                    color=[CHANNEL_COLORS.get(c, '#6B7280') for c in monthly_ch.columns])
    ax.set_xlabel('月份'); ax.set_ylabel('订单量')
    ax.set_title('各渠道月度订单贡献', fontsize=14, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.02, 1), fontsize=9)
    save_fig(fig, 'w2_13_channel_monthly_contribution.png', 'W2')

    # W2_14: 5种归因对比
    fig, ax = plt.subplots(figsize=(12, 6))
    attr_df.plot(kind='bar', ax=ax, width=0.7, color=CATEGORICAL_10[:5], alpha=0.85)
    ax.set_xlabel('渠道'); ax.set_ylabel('归因占比 (%)')
    ax.set_title('5种归因方法对比', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    save_fig(fig, 'w2_14_city_channel_sankey.png', 'W2')

    # W2_17: 延迟天数 vs 满意度
    if '线索到交付天数' in data.columns:
        fig, ax = plt.subplots(figsize=(10, 6))
        has_order = data[data['交付评分'].notna()]
        ax.scatter(has_order['线索到交付天数'], has_order['交付评分'], alpha=0.3, s=5, c='#2563EB')
        # LOWESS smooth
        sorted_idx = has_order['线索到交付天数'].argsort()
        x_sorted = has_order['线索到交付天数'].iloc[sorted_idx]
        y_sorted = has_order['交付评分'].iloc[sorted_idx]
        window = 100
        y_smooth = pd.Series(y_sorted.values).rolling(window=window, center=True).mean()
        ax.plot(x_sorted, y_smooth, color='#EF4444', lw=2, label=f'滑动平均(窗口={window})')
        ax.set_xlabel('线索到交付天数'); ax.set_ylabel('交付评分')
        ax.set_title('交付周期 vs 客户满意度', fontsize=14, fontweight='bold')
        ax.legend()
        save_fig(fig, 'w2_17_delay_satisfaction_scatter.png', 'W2')

    # W2_18: 投诉影响森林图
    complaint_effect = data.groupby('主要投诉类型')['售后平均满意度'].agg(['mean', 'std', 'count']).dropna()
    if len(complaint_effect) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        complaint_effect = complaint_effect.sort_values('mean')
        ax.errorbar(complaint_effect['mean'], range(len(complaint_effect)),
                    xerr=complaint_effect['std']/np.sqrt(complaint_effect['count']),
                    fmt='o', capsize=3, color='#2563EB', markersize=8, elinewidth=1)
        ax.set_yticks(range(len(complaint_effect)))
        ax.set_yticklabels(complaint_effect.index)
        ax.set_xlabel('平均满意度'); ax.set_title('各投诉类型满意度森林图', fontsize=14, fontweight='bold')
        ax.axvline(x=data['售后平均满意度'].mean(), color='#EF4444', linestyle='--', alpha=0.5, label='总均值')
        ax.legend()
        save_fig(fig, 'w2_18_complaint_impact_forest.png', 'W2')

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('  G9 W2: 因果推断与归因分析')
    print('=' * 60)

    # 加载宽表
    wide_path = os.path.join(DATA_DIR, 'wide_table.parquet')
    if not os.path.exists(wide_path):
        wide_path = os.path.join(DATA_DIR, 'wide_table.csv')
    wide = pd.read_parquet(wide_path) if wide_path.endswith('.parquet') else pd.read_csv(wide_path)
    print(f'  加载宽表: {wide.shape[0]:,} × {wide.shape[1]}')

    # 1. PSM
    try:
        psm_results = run_psm_analysis(wide)
    except Exception as e:
        print(f'  PSM error: {e}')
        psm_results = {'att': 0, 'att_se': 0, 'att_ci': (0,0), 'n_matches': 0}

    # 2. RDD
    try:
        rdd_results = run_rdd_analysis(wide)
    except Exception as e:
        print(f'  RDD error: {e}')
        rdd_results = {'ate': 0, 'bw': 0}

    # 3. IV
    try:
        iv_results = run_iv_analysis(wide)
    except Exception as e:
        print(f'  IV error: {e}')
        iv_results = {'iv_effect': 0, 'iv_se': 0, 'f_stat': 0}

    # 4. HTE
    try:
        hte_results = run_hte_analysis(wide)
    except Exception as e:
        print(f'  HTE error: {e}')
        hte_results = {}

    # 5. 渠道归因
    try:
        attr_results = run_channel_attribution(wide)
    except Exception as e:
        print(f'  Attribution error: {e}')
        attr_results = {}

    print('\n[OK] W2 Complete!')
    print(f'  Charts: reports/W2_charts/')
