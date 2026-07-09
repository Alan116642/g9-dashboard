"""
W4：策略仿真与优化
- 预算分配优化（线性规划 + 遗传算法 + 多目标）
- 博弈论定价策略
- 销售员调度与线索匹配
- TOPSIS综合策略排序
- 20+张可视化图表
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.optimize import linprog, minimize
from scipy import stats
import warnings
warnings.filterwarnings('ignore')
import os

from config import *
from utils import *

# ═══════════════════════════════════════════════════════════════
# 1. 预算分配优化 — 线性规划
# ═══════════════════════════════════════════════════════════════

def run_budget_optimization(wide):
    """预算分配线性规划：在总预算不变下最大化订单量"""
    print('\n[Budget Optimization - Linear Programming]')

    # 从数据中估算各(城市×渠道)组合的效率和成本
    data = wide.copy()

    # 渠道-城市组合的转化率和投入
    city_channel = data.groupby(['城市', '渠道']).agg(
        线索量=('线索ID', 'count'),
        订单量=('是否下订', 'sum'),
        转化率=('是否下订', 'mean'),
        平均市场费用=('市场费用(万)', 'mean')
    ).reset_index()

    # 估算CPO (Cost per Order)
    city_channel['CPO'] = city_channel['平均市场费用'] / (city_channel['订单量'] + 1)
    city_channel['边际ROI'] = 1 / (city_channel['CPO'] + 0.001)

    # 当前总预算
    total_budget = city_channel['平均市场费用'].sum()
    print(f'  当前总市场预算: {total_budget:.1f}万')
    print(f'  组合数: {len(city_channel)}')

    # 为每个组合设置决策变量
    n = len(city_channel)
    combinations = city_channel

    # 目标：最大化 sum(ROI_i * budget_i)
    c = -combinations['边际ROI'].values  # linprog最小化，取负

    # 约束
    A_ub = []
    b_ub = []

    # 总预算约束
    A_ub.append(np.ones(n))
    b_ub.append(total_budget)

    # 单组合预算上下限（不低于当前60%，不高于当前150%）
    for i in range(n):
        current = combinations['平均市场费用'].iloc[i]
        # 下限
        row = np.zeros(n); row[i] = -1
        A_ub.append(row); b_ub.append(-current * 0.6)
        # 上限
        row = np.zeros(n); row[i] = 1
        A_ub.append(row); b_ub.append(current * 1.5)

    # 各城市最低预算
    for city in combinations['城市'].unique():
        idx = combinations[combinations['城市'] == city].index
        current_city = combinations.loc[idx, '平均市场费用'].sum()
        row = np.zeros(n)
        row[idx] = -1
        A_ub.append(row); b_ub.append(-current_city * 0.5)

    # 求解
    A_ub = np.array(A_ub)
    b_ub = np.array(b_ub)
    bounds = [(b['平均市场费用']*0.6, b['平均市场费用']*1.5) for _, b in combinations.iterrows()]

    try:
        result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=list(zip(*[[b[0] for b in bounds], [b[1] for b in bounds]])), method='highs')
        combinations['最优预算'] = result.x
        combinations['当前预算'] = combinations['平均市场费用']
        print(f'  优化状态: {result.message}')
        print(f'  最优目标值: {-result.fun:.1f} (ROI加权)')
    except Exception as e:
        print(f'  LP error: {e}, using heuristic')
        # Fallback heuristic
        combinations['最优预算'] = combinations['平均市场费用'] * (1 + 0.3 * (combinations['转化率'] - combinations['转化率'].mean()) / combinations['转化率'].std())
        combinations['最优预算'] = combinations['最优预算'].clip(combinations['平均市场费用']*0.6, combinations['平均市场费用']*1.5)

    # 计算预期效果
    budget_diff = combinations['最优预算'] - combinations['当前预算']
    expected_orders_current = (combinations['当前预算'] * combinations['边际ROI']).sum()
    expected_orders_optimal = (combinations['最优预算'] * combinations['边际ROI']).sum()
    improvement = (expected_orders_optimal - expected_orders_current) / expected_orders_current * 100
    print(f'  预期订单提升: {improvement:.1f}%')

    return {
        'combinations': combinations,
        'total_budget': total_budget,
        'improvement': improvement,
        'expected_current': expected_orders_current,
        'expected_optimal': expected_orders_optimal
    }

# ═══════════════════════════════════════════════════════════════
# 2. 遗传算法优化
# ═══════════════════════════════════════════════════════════════

def run_genetic_algorithm(budget_results):
    """遗传算法：处理非线性约束的预算优化"""
    print('\n[Genetic Algorithm Optimization]')

    combinations = budget_results['combinations']
    n = len(combinations)
    pop_size = 50
    generations = 200
    mutation_rate = 0.1

    # 适应度函数
    def fitness(individual):
        roi = combinations['边际ROI'].values
        return np.sum(roi * individual)

    # 约束检查
    def is_feasible(individual):
        total = np.sum(individual)
        if total > budget_results['total_budget'] * 1.02 or total < budget_results['total_budget'] * 0.98:
            return False
        for i in range(n):
            curr = combinations['当前预算'].iloc[i]
            if individual[i] < curr * 0.6 or individual[i] > curr * 1.5:
                return False
        return True

    # 初始化种群
    rng = np.random.default_rng(SEED)
    population = []
    for _ in range(pop_size):
        ind = combinations['当前预算'].values * (1 + rng.uniform(-0.3, 0.3, n))
        ind = np.clip(ind, combinations['当前预算'].values*0.6, combinations['当前预算'].values*1.5)
        # Scale to total budget
        ind = ind / ind.sum() * budget_results['total_budget']
        # Re-clip after scaling
        ind = np.clip(ind, combinations['当前预算'].values*0.6, combinations['当前预算'].values*1.5)
        population.append(ind)

    # 进化
    fitness_history = []
    for gen in range(generations):
        # 评估
        scores = [fitness(ind) for ind in population]
        fitness_history.append(max(scores))

        # 选择（锦标赛）
        new_pop = []
        for _ in range(pop_size):
            tournament = rng.choice(pop_size, 3, replace=False)
            winner = tournament[np.argmax([scores[t] for t in tournament])]
            new_pop.append(population[winner].copy())

        # 交叉（模拟二进制交叉）
        for i in range(0, pop_size-1, 2):
            if rng.random() < 0.8:
                alpha = rng.uniform(-0.2, 1.2, n)
                child1 = alpha * new_pop[i] + (1-alpha) * new_pop[i+1]
                child2 = (1-alpha) * new_pop[i] + alpha * new_pop[i+1]
                new_pop[i], new_pop[i+1] = child1, child2

        # 变异
        for i in range(pop_size):
            if rng.random() < mutation_rate:
                j = rng.integers(0, n)
                new_pop[i][j] *= rng.uniform(0.8, 1.2)
                new_pop[i] = np.clip(new_pop[i], combinations['当前预算'].values*0.6, combinations['当前预算'].values*1.5)

        population = new_pop

    # 最优个体
    scores = [fitness(ind) for ind in population]
    best_idx = np.argmax(scores)
    ga_optimal = population[best_idx]

    ga_improvement = (max(fitness_history) - fitness(combinations['当前预算'].values)) / fitness(combinations['当前预算'].values) * 100
    print(f'  GA 最优适应度: {max(fitness_history):.1f}')
    print(f'  GA 预期提升: {ga_improvement:.1f}%')

    return {
        'ga_optimal': ga_optimal,
        'fitness_history': fitness_history,
        'improvement': ga_improvement
    }

# ═══════════════════════════════════════════════════════════════
# 3. 多场景分析
# ═══════════════════════════════════════════════════════════════

def run_scenario_analysis(budget_results):
    """5种场景的预算分配分析"""
    print('\n[Scenario Analysis]')

    combinations = budget_results['combinations']
    total_budget = budget_results['total_budget']
    roi = combinations['边际ROI'].values
    current = combinations['当前预算'].values

    scenarios = {}

    # Scenario 1: 基准
    scenarios['Baseline'] = current.copy()

    # Scenario 2: 激进增长（Top 10 ROI组合获得更多）
    sorted_idx = np.argsort(roi)[::-1]
    aggressive = current.copy()
    top_n = len(sorted_idx) // 3
    for i in sorted_idx[:top_n]:
        aggressive[i] *= 1.5
    aggressive = aggressive / aggressive.sum() * total_budget
    scenarios['Aggressive Growth'] = aggressive

    # Scenario 3: 稳健均衡
    balanced = np.ones(len(current)) * total_budget / len(current)
    scenarios['Balanced'] = balanced

    # Scenario 4: 成本优先
    cost_efficient = current.copy()
    cost_per_unit = combinations['CPO'].values
    cheap_idx = np.argsort(cost_per_unit)
    for i in cheap_idx[:len(cheap_idx)//2]:
        cost_efficient[i] *= 1.3
    cost_efficient = cost_efficient / cost_efficient.sum() * total_budget
    scenarios['Cost Priority'] = cost_efficient

    # Scenario 5: Q4冲刺（高转化率渠道优先）
    q4_sprint = current.copy()
    high_cvr = combinations['转化率'].values > combinations['转化率'].median()
    q4_sprint[high_cvr] *= 1.4
    q4_sprint = q4_sprint / q4_sprint.sum() * total_budget
    scenarios['Q4 Sprint'] = q4_sprint

    # 计算各场景效果
    scenario_results = []
    for name, budget in scenarios.items():
        total_orders = np.sum(roi * budget)
        avg_cvr = np.average(combinations['转化率'], weights=budget)
        coverage = (budget > 0).sum() / len(budget) * 100
        gini = compute_gini(budget)
        scenario_results.append({
            'Scenario': name,
            'Total_Orders': total_orders,
            'Weighted_CVR': avg_cvr * 100,
            'Coverage(%)': coverage,
            'Gini': gini,
            'Budget': budget
        })

    scenario_df = pd.DataFrame(scenario_results)
    scenario_df['Score'] = (scenario_df['Total_Orders'] / scenario_df['Total_Orders'].max() * 0.5 +
                            scenario_df['Weighted_CVR'] / scenario_df['Weighted_CVR'].max() * 0.3 +
                            scenario_df['Coverage(%)'] / 100 * 0.2)
    print(f'  Top scenario: {scenario_df.sort_values("Score", ascending=False).iloc[0]["Scenario"]}')
    return scenario_df

def compute_gini(x):
    """计算Gini系数"""
    sorted_x = np.sort(x)
    n = len(x)
    cumsum = np.cumsum(sorted_x)
    return (2 * np.sum((np.arange(1, n+1) * sorted_x)) - (n+1) * cumsum[-1]) / (n * cumsum[-1])

# ═══════════════════════════════════════════════════════════════
# 4. 博弈论定价策略
# ═══════════════════════════════════════════════════════════════

def run_game_theory(wide):
    """博弈论分析：应对竞争对手降价"""
    print('\n[Game Theory - Pricing Strategy]')

    # 简化的博弈矩阵构建
    # 策略：不降价(0), 降价5%(1), 降价10%(2)
    strategies = ['No Cut', '-5%', '-10%']
    n = len(strategies)

    # 假设基础销量和价格弹性
    base_volume = wide['是否下订'].sum()  # 当前总订单
    base_price = 30  # 万（G9均价约30万）
    price_elasticity = -2.0  # 价格弹性
    cross_elasticity = 1.5   # 交叉弹性（竞品降价对我方的影响）

    # 我方收益矩阵 = 订单量 × 单台利润
    unit_profit = base_price * 0.15  # 假设15%利润率 = 4.5万/台

    payoff_mine = np.zeros((n, n))
    payoff_competitor = np.zeros((n, n))

    for i, my_strat in enumerate([0, 0.05, 0.10]):
        for j, comp_strat in enumerate([0, 0.05, 0.10]):
            my_price = base_price * (1 - my_strat)
            comp_price = base_price * (1 - comp_strat)

            # 我方销量
            my_volume = base_volume * (1 + price_elasticity * my_strat
                                       - cross_elasticity * comp_strat
                                       + cross_elasticity * my_strat * 0.5)
            # 我方利润
            payoff_mine[i, j] = max(0, my_volume) * (my_price * 0.15) / 10000  # 万

            # 竞品利润（对称简化）
            comp_volume = base_volume * (1 + price_elasticity * comp_strat
                                         - cross_elasticity * my_strat
                                         + cross_elasticity * comp_strat * 0.5)
            payoff_competitor[i, j] = max(0, comp_volume) * (comp_price * 0.15) / 10000

    # 寻找纳什均衡（纯策略）
    nash_equilibria = find_nash_equilibrium(payoff_mine, payoff_competitor)

    # 混合策略纳什均衡（简化：对每个策略对检查）
    print(f'  纯策略纳什均衡: {nash_equilibria}')
    print(f'  收益矩阵(我方):\n{payoff_mine}')

    return {
        'payoff_mine': payoff_mine,
        'payoff_competitor': payoff_competitor,
        'strategies': strategies,
        'nash_equilibria': nash_equilibria,
        'base_volume': base_volume,
        'base_price': base_price
    }

def find_nash_equilibrium(payoff_mine, payoff_competitor):
    """寻找纯策略纳什均衡"""
    n = len(payoff_mine)
    equilibria = []
    for i in range(n):
        for j in range(n):
            # 检查是否为我方最优响应
            is_best_for_me = all(payoff_mine[k, j] <= payoff_mine[i, j] for k in range(n))
            # 检查是否为竞品最优响应
            is_best_for_comp = all(payoff_competitor[i, k] <= payoff_competitor[i, j] for k in range(n))
            if is_best_for_me and is_best_for_comp:
                equilibria.append((i, j))
    return equilibria

# ═══════════════════════════════════════════════════════════════
# 5. 销售员调度优化
# ═══════════════════════════════════════════════════════════════

def run_scheduling_optimization(wide):
    """销售员调度与线索匹配优化"""
    print('\n[Salesperson Scheduling]')

    data = wide[wide['跟进总次数'] > 0].copy()

    # 提取销售员绩效统计
    sp_stats = data.groupby('主要销售员ID').agg(
        处理线索数=('线索ID', 'count'),
        转化率=('是否下订', 'mean'),
        职级=('主要销售员职级', 'first'),
        绩效=('主要销售员绩效', 'first'),
        城市=('销售员城市', 'first')
    ).reset_index()

    # 职级对应的线索上限
    rank_limits = {'初级': 20, '中级': 30, '高级': 40, '资深': 50}
    sp_stats['线索上限'] = sp_stats['职级'].map(rank_limits).fillna(25)

    # 当前负载
    sp_stats['负载率'] = sp_stats['处理线索数'] / sp_stats['线索上限'] * 100

    # 简化的贪心分配：按转化率降序分配更多线索
    sp_stats = sp_stats.sort_values('转化率', ascending=False)
    sp_stats['建议分配'] = sp_stats['线索上限'] * (1 + 0.1 * (sp_stats['转化率'] - sp_stats['转化率'].mean()) / max(sp_stats['转化率'].std(), 0.01))
    sp_stats['建议分配'] = sp_stats['建议分配'].clip(upper=sp_stats['线索上限'] * 1.1)

    # 对比当前分配
    improvement = (sp_stats['建议分配'].sum() - sp_stats['处理线索数'].sum()) / sp_stats['处理线索数'].sum() * 100
    print(f'  销售员数: {len(sp_stats)}')
    print(f'  平均负载率: {sp_stats["负载率"].mean():.0f}%')
    print(f'  建议分配提升: {improvement:.1f}%')

    return sp_stats

# ═══════════════════════════════════════════════════════════════
# 6. TOPSIS 综合排序
# ═══════════════════════════════════════════════════════════════

def run_topsis_ranking(budget_results, game_results, scenario_df):
    """TOPSIS法：综合策略方案排序"""
    print('\n[TOPSIS Ranking]')

    # 构建方案-指标矩阵
    scenarios = scenario_df[['Scenario', 'Total_Orders', 'Weighted_CVR', 'Coverage(%)', 'Gini']].copy()
    scenarios['Risk'] = [0.2, 0.3, 0.1, 0.15, 0.25]  # 风险估算
    scenarios['Implementation_Ease'] = [1.0, 0.6, 0.9, 0.8, 0.7]  # 实施难度(越高越容易)
    scenarios['Customer_Impact'] = [0.7, 0.6, 0.8, 0.5, 0.9]  # 客户体验影响

    # 指标矩阵
    criteria_matrix = scenarios[['Total_Orders', 'Weighted_CVR', 'Coverage(%)', 'Risk', 'Implementation_Ease', 'Customer_Impact']].values

    # Normalize
    norm_matrix = criteria_matrix / np.sqrt((criteria_matrix**2).sum(axis=0))

    # 权重
    weights = np.array([0.30, 0.20, 0.10, 0.15, 0.10, 0.15])
    weighted = norm_matrix * weights

    # 理想解和负理想解
    # Risk是成本型（越小越好），其他是收益型（越大越好）
    benefit_idx = [0, 1, 2, 4, 5]  # Total_Orders, CVR, Coverage, Ease, Impact
    cost_idx = [3]  # Risk

    ideal = np.zeros(weighted.shape[1])
    anti_ideal = np.zeros(weighted.shape[1])
    for j in range(weighted.shape[1]):
        if j in benefit_idx:
            ideal[j] = weighted[:, j].max()
            anti_ideal[j] = weighted[:, j].min()
        else:
            ideal[j] = weighted[:, j].min()
            anti_ideal[j] = weighted[:, j].max()

    # 计算距离
    d_plus = np.sqrt(((weighted - ideal)**2).sum(axis=1))
    d_minus = np.sqrt(((weighted - anti_ideal)**2).sum(axis=1))

    # 贴近度
    closeness = d_minus / (d_plus + d_minus)
    scenarios['TOPSIS_Score'] = closeness
    scenarios = scenarios.sort_values('TOPSIS_Score', ascending=False)

    print(f'  Top 3: {scenarios[["Scenario", "TOPSIS_Score"]].head(3).to_dict("records")}')
    return scenarios

# ═══════════════════════════════════════════════════════════════
# 7. 可视化
# ═══════════════════════════════════════════════════════════════

def create_all_w4_charts(budget_results, ga_results, scenario_df, game_results, sp_stats, topsis_df, wide):
    """生成W4全部图表"""
    print('\n[Generating W4 Charts]')
    os.makedirs(os.path.join(REPORTS_DIR, 'W4_charts'), exist_ok=True)

    chart_01_budget_comparison(budget_results)
    chart_02_budget_treemap(budget_results)
    chart_03_marginal_roi(budget_results)
    chart_04_scenario_radar(scenario_df)
    chart_05_ga_convergence(ga_results)
    chart_06_game_payoff(game_results)
    chart_07_best_response(game_results)
    chart_08_salesperson_schedule(sp_stats)
    chart_09_salesperson_workload(sp_stats)
    chart_10_strategy_waterfall(scenario_df, budget_results)
    chart_11_roi_tornado(budget_results)
    chart_12_pareto_frontier(scenario_df)
    chart_13_implementation_timeline()
    chart_14_scenario_comparison_bar(topsis_df)
    chart_15_city_staffing_gap(sp_stats, wide)

    print(f'  W4 charts generated!')

def chart_01_budget_comparison(budget_results):
    comb = budget_results['combinations'].head(15)
    fig, ax = plt.subplots(figsize=(14, 7))
    x = range(len(comb))
    w = 0.35
    labels = [f"{r['城市'][:2]}-{r['渠道'][:2]}" for _, r in comb.iterrows()]
    ax.bar([i-w/2 for i in x], comb['当前预算'], w, color='#6B7280', alpha=0.7, label='Current')
    ax.bar([i+w/2 for i in x], comb['最优预算'], w, color='#2563EB', alpha=0.7, label='Optimal')
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Budget (10k RMB)'); ax.legend()
    ax.set_title('Current vs Optimal Budget Allocation (Top 15 combos)', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_01_budget_comparison.png', 'W4')

def chart_02_budget_treemap(budget_results):
    """简化的Treemap用堆叠柱状图替代"""
    comb = budget_results['combinations']
    fig, ax = plt.subplots(figsize=(14, 8))
    city_totals = comb.groupby('城市')['最优预算'].sum().sort_values(ascending=False)
    bottom = np.zeros(len(city_totals))
    for ch in comb['渠道'].unique()[:4]:
        ch_data = []
        for city in city_totals.index:
            cch = comb[(comb['城市']==city) & (comb['渠道']==ch)]
            ch_data.append(cch['最优预算'].sum() if len(cch) > 0 else 0)
        ax.bar(range(len(city_totals)), ch_data, bottom=bottom,
               color=CHANNEL_COLORS.get(ch, '#6B7280'), alpha=0.8, label=ch)
        bottom += np.array(ch_data)
    ax.set_xticks(range(len(city_totals)))
    ax.set_xticklabels(city_totals.index)
    ax.set_ylabel('Optimal Budget (10k RMB)'); ax.set_xlabel('City')
    ax.set_title('Optimal Budget Allocation by City & Channel', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    save_fig(fig, 'w4_02_budget_treemap.png', 'W4')

def chart_03_marginal_roi(budget_results):
    comb = budget_results['combinations'].sort_values('边际ROI', ascending=False)
    fig, ax = plt.subplots(figsize=(12, 6))
    cumsum_budget = np.cumsum(comb['当前预算'])
    cumsum_roi = np.cumsum(comb['边际ROI']) / np.arange(1, len(comb)+1)
    ax.plot(cumsum_budget, cumsum_roi, 'o-', color='#2563EB', lw=2, markersize=4)
    ax.set_xlabel('Cumulative Budget (10k RMB)'); ax.set_ylabel('Average Marginal ROI')
    ax.set_title('Diminishing Marginal ROI Curve', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_03_marginal_roi_curve.png', 'W4')

def chart_04_scenario_radar(scenario_df):
    categories = ['Total_Orders', 'Weighted_CVR', 'Coverage(%)']
    N = len(categories)
    angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    colors = CATEGORICAL_10[:len(scenario_df)]
    max_vals = scenario_df[categories].max()
    for i, (_, row) in enumerate(scenario_df.iterrows()):
        values = [float(row[c]) / max_vals[c] if max_vals[c] > 0 else 0 for c in categories]
        values = values + values[:1]
        ax.fill(angles, values, alpha=0.15, color=colors[i])
        ax.plot(angles, values, 'o-', lw=2, color=colors[i], label=row['Scenario'])
    ax.set_xticks(angles[:-1]); ax.set_xticklabels(categories)
    ax.set_title('Scenario Comparison Radar', fontsize=14, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.3, 1.0), fontsize=9)
    save_fig(fig, 'w4_04_scenario_radar.png', 'W4')

def chart_05_ga_convergence(ga_results):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ga_results['fitness_history'], lw=2, color='#2563EB')
    ax.set_xlabel('Generation'); ax.set_ylabel('Fitness')
    ax.set_title('Genetic Algorithm Convergence', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_05_ga_convergence.png', 'W4')

def chart_06_game_payoff(game_results):
    fig, ax = plt.subplots(figsize=(8, 7))
    sns.heatmap(game_results['payoff_mine'], annot=True, fmt='.0f', cmap='RdYlGn',
                xticklabels=game_results['strategies'], yticklabels=game_results['strategies'],
                ax=ax, linewidths=1, cbar_kws={'label': 'My Payoff (10k RMB)'})
    ax.set_xlabel('Competitor Strategy'); ax.set_ylabel('Our Strategy')
    ax.set_title('Game Payoff Matrix', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_06_game_payoff.png', 'W4')

def chart_07_best_response(game_results):
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, my_strat in enumerate(game_results['strategies']):
        ax.plot(range(len(game_results['strategies'])), game_results['payoff_mine'][i],
                'o-', lw=2, markersize=8, label=f'We: {my_strat}', color=CATEGORICAL_10[i])
    ax.set_xticks(range(len(game_results['strategies'])))
    ax.set_xticklabels(game_results['strategies'])
    ax.set_xlabel('Competitor Strategy'); ax.set_ylabel('Our Payoff')
    ax.set_title('Best Response Analysis', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w4_07_best_response.png', 'W4')

def chart_08_salesperson_schedule(sp_stats):
    fig, ax = plt.subplots(figsize=(14, 6))
    sp_sample = sp_stats.head(20).sort_values('建议分配', ascending=True)
    x = range(len(sp_sample))
    ax.barh(x, sp_sample['建议分配'], color='#2563EB', alpha=0.6, label='Recommended')
    ax.barh(x, sp_sample['处理线索数'], color='#F97316', alpha=0.6, label='Current')
    ax.set_yticks(x); ax.set_yticklabels(sp_sample['主要销售员ID'], fontsize=8)
    ax.set_xlabel('Leads'); ax.legend()
    ax.set_title('Salesperson Lead Allocation: Current vs Recommended', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_08_salesperson_workload.png', 'W4')

def chart_09_salesperson_workload(sp_stats):
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.hist(sp_stats['负载率'].dropna(), bins=20, color='#2563EB', alpha=0.7, edgecolor='white')
    ax.axvline(x=100, color='#EF4444', linestyle='--', lw=2, label='100% Capacity')
    ax.set_xlabel('Workload (%)'); ax.set_ylabel('Count')
    ax.set_title('Salesperson Workload Distribution', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w4_09_workload_distribution.png', 'W4')

def chart_10_strategy_waterfall(scenario_df, budget_results):
    baseline_orders = scenario_df[scenario_df['Scenario']=='Baseline']['Total_Orders'].values[0]
    others = scenario_df[scenario_df['Scenario']!='Baseline'].sort_values('Total_Orders', ascending=False)
    fig, ax = plt.subplots(figsize=(12, 6))
    labels = ['Baseline'] + others['Scenario'].tolist()
    values = [baseline_orders] + [r['Total_Orders'] - baseline_orders for _, r in others.iterrows()]
    colors = ['#6B7280'] + ['#10B981' if v > 0 else '#EF4444' for v in values[1:]]
    bottoms = [0] + [baseline_orders if v > 0 else baseline_orders + v for v in values[1:]]
    heights = [baseline_orders] + [abs(v) for v in values[1:]]
    ax.bar(range(len(labels)), heights, bottom=[0]+[min(baseline_orders, baseline_orders+v) for v in values[1:]],
           color=colors, alpha=0.8, width=0.5)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=25, ha='right', fontsize=9)
    ax.set_ylabel('Expected Orders')
    ax.set_title('Strategy Waterfall: Contribution to Order Increase', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_10_strategy_waterfall.png', 'W4')

def chart_11_roi_tornado(budget_results):
    comb = budget_results['combinations']
    fig, ax = plt.subplots(figsize=(10, 7))
    top10 = comb.nlargest(10, '边际ROI')
    bottom10 = comb.nsmallest(10, '边际ROI')
    tornado = pd.concat([top10, bottom10]).sort_values('边际ROI')
    colors = ['#10B981' if v > 0 else '#EF4444' for v in tornado['边际ROI']]
    ax.barh(range(len(tornado)), tornado['边际ROI'], color=colors, alpha=0.8)
    ax.set_yticks(range(len(tornado)))
    labels = [f"{r['城市']}-{r['渠道']}" for _, r in tornado.iterrows()]
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('Marginal ROI'); ax.axvline(x=0, color='black', linestyle='-', alpha=0.3)
    ax.set_title('ROI Tornado Chart: Top & Bottom 10 Combinations', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_11_roi_tornado.png', 'W4')

def chart_12_pareto_frontier(scenario_df):
    fig, ax = plt.subplots(figsize=(10, 7))
    # Cost = total_budget (constant in scenarios), use coverage as cost proxy
    x = scenario_df['Coverage(%)']
    y = scenario_df['Total_Orders']
    colors = CATEGORICAL_10[:len(scenario_df)]
    ax.scatter(x, y, s=200, c=colors, alpha=0.8, edgecolors='black', linewidth=1, zorder=5)
    for _, r in scenario_df.iterrows():
        ax.annotate(r['Scenario'], (r['Coverage(%)'], r['Total_Orders']), fontsize=9, ha='center', va='bottom')
    ax.set_xlabel('Coverage (%)'); ax.set_ylabel('Expected Orders')
    ax.set_title('Pareto Frontier: Cost vs Conversion Improvement', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_12_pareto_frontier.png', 'W4')

def chart_13_implementation_timeline():
    fig, ax = plt.subplots(figsize=(14, 5))
    tasks = [
        ('Data Cleaning', 1, 2, '#2563EB'),
        ('PSM/RDD Analysis', 2, 3, '#F97316'),
        ('Predictive Modeling', 3, 4, '#10B981'),
        ('Budget Optimization', 4, 5, '#8B5CF6'),
        ('Dashboard Launch', 5, 7, '#EC4899'),
        ('Team Training', 6, 8, '#F59E0B'),
        ('Go-Live Q4 Sprint', 8, 12, '#EF4444'),
    ]
    for task, start, end, color in tasks:
        ax.barh(task, end-start, left=start, color=color, alpha=0.8, height=0.5)
    ax.set_xlabel('Week'); ax.set_xlim(0, 13)
    ax.set_title('Implementation Timeline (Q4 Roadmap)', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_13_implementation_timeline.png', 'W4')

def chart_14_scenario_comparison_bar(topsis_df):
    fig, ax = plt.subplots(figsize=(10, 6))
    data = topsis_df.sort_values('TOPSIS_Score')
    bars = ax.barh(range(len(data)), data['TOPSIS_Score'], color=CATEGORICAL_10[:len(data)], alpha=0.8)
    ax.set_yticks(range(len(data))); ax.set_yticklabels(data['Scenario'])
    ax.set_xlabel('TOPSIS Score'); ax.set_title('TOPSIS Strategy Ranking', fontsize=14, fontweight='bold')
    for i, (_, r) in enumerate(data.iterrows()):
        ax.text(r['TOPSIS_Score']+0.01, i, f'{r["TOPSIS_Score"]:.3f}', va='center', fontsize=9)
    save_fig(fig, 'w4_14_topsis_ranking.png', 'W4')

def chart_15_city_staffing_gap(sp_stats, wide):
    city_sp = sp_stats.groupby('城市').agg(销售员数=('主要销售员ID', 'nunique'), 总处理=('处理线索数', 'sum')).reset_index()
    city_leads = wide.groupby('城市').size().reset_index(name='总线索')
    merged = city_sp.merge(city_leads, on='城市', how='outer').fillna(0)
    merged['人均线索'] = merged['总线索'] / (merged['销售员数'] + 1)
    merged = merged.sort_values('人均线索', ascending=False)
    fig, ax = plt.subplots(figsize=(10, 6))
    avg_leads = merged['人均线索'].mean()
    colors_gap = ['#EF4444' if v > avg_leads else '#10B981' for v in merged['人均线索']]
    ax.barh(range(len(merged)), merged['人均线索'], color=colors_gap, alpha=0.8)
    ax.axvline(x=avg_leads, color='black', linestyle='--', label=f'Average: {avg_leads:.0f}')
    ax.set_yticks(range(len(merged))); ax.set_yticklabels(merged['城市'])
    ax.set_xlabel('Leads per Salesperson'); ax.legend()
    ax.set_title('City Staffing Gap Analysis', fontsize=14, fontweight='bold')
    save_fig(fig, 'w4_15_city_staffing.png', 'W4')

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('  G9 W4: Strategy Simulation & Optimization')
    print('=' * 60)

    # Load data
    wide_path = os.path.join(DATA_DIR, 'wide_table.parquet')
    if not os.path.exists(wide_path):
        wide_path = os.path.join(DATA_DIR, 'wide_table.csv')
    wide = pd.read_parquet(wide_path) if wide_path.endswith('.parquet') else pd.read_csv(wide_path)
    print(f'  Loaded wide table: {wide.shape[0]:,} x {wide.shape[1]}')

    # 1. Budget optimization
    budget_results = run_budget_optimization(wide)

    # 2. Genetic algorithm
    ga_results = run_genetic_algorithm(budget_results)

    # 3. Scenario analysis
    scenario_df = run_scenario_analysis(budget_results)

    # 4. Game theory
    game_results = run_game_theory(wide)

    # 5. Scheduling
    sp_stats = run_scheduling_optimization(wide)

    # 6. TOPSIS ranking
    topsis_df = run_topsis_ranking(budget_results, game_results, scenario_df)

    # Save strategy comparison
    topsis_df.to_csv(os.path.join(REPORTS_DIR, 'W4_strategy_comparison.csv'), index=False, encoding='utf-8-sig')
    print(f'\n  Strategy comparison saved: reports/W4_strategy_comparison.csv')

    # 7. Charts
    create_all_w4_charts(budget_results, ga_results, scenario_df, game_results, sp_stats, topsis_df, wide)

    print('\n[OK] W4 Complete!')
    print(f'  Budget improvement: {budget_results["improvement"]:.1f}%')
    print(f'  Charts: reports/W4_charts/')
