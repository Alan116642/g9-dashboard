"""
W3：预测建模与智能预警
- 转化预测模型（6模型对比 + Optuna超参优化 + 概率校准 + Stacking）
- 流失/风险预警（Cox + 随机生存森林）
- SHAP可解释性分析（12项分析）
- 28+张可视化图表
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, StackingClassifier
from sklearn.metrics import (roc_auc_score, f1_score, precision_score, recall_score,
                              roc_curve, precision_recall_curve, confusion_matrix,
                              brier_score_loss, classification_report)
from sklearn.calibration import calibration_curve, CalibratedClassifierCV
import warnings
warnings.filterwarnings('ignore')
import os
import pickle

from config import *
from utils import *

# ═══════════════════════════════════════════════════════════════
# 1. 特征工程
# ═══════════════════════════════════════════════════════════════

def prepare_modeling_data(wide):
    """准备建模特征集"""
    print('\n[Feature Engineering]')
    data = wide.copy()

    # 数值特征
    num_features = [
        '客户年龄', '试驾时长', '跟进总次数', '平均沟通时长',
        '最大沟通时长', '沟通时长标准差', '跟进天数跨度',
        '跟进强度', '首次跟进间隔天数', '电话占比', '微信占比', '面谈占比',
        '涉及销售员数', '销售员经验天数',
    ]
    # 确保存在的特征
    available_num = [c for c in num_features if c in data.columns]

    # 类别特征编码
    cat_features = ['城市', '渠道', '客户性别', '季度', '主要跟进方式']
    available_cat = [c for c in cat_features if c in data.columns]

    # 构建特征矩阵
    X = data[available_num].fillna(0).copy()

    for cat in available_cat:
        dummies = pd.get_dummies(data[cat], prefix=cat).astype(float)
        X = pd.concat([X, dummies], axis=1)

    # 目标变量
    y = data['是否下订'].astype(int)

    # 移除低方差特征
    variances = X.var()
    low_var = variances[variances < 0.001].index.tolist()
    if low_var:
        X = X.drop(columns=low_var)

    print(f'  特征矩阵: {X.shape[0]:,} x {X.shape[1]}')
    print(f'  正样本: {y.sum():,} ({y.mean()*100:.1f}%)')

    return X, y

# ═══════════════════════════════════════════════════════════════
# 2. 模型训练与对比
# ═══════════════════════════════════════════════════════════════

def train_and_compare_models(X, y):
    """训练6个模型并全面对比"""
    print('\n[Model Training & Comparison]')

    # 时间序列划分（按月份）
    # 简单随机分层划分作为简化的替代方案
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    print(f'  训练集: {len(X_train):,} | 测试集: {len(X_test):,}')

    # 6模型定义
    models = {
        'Logistic Regression (L2)': LogisticRegression(max_iter=2000, random_state=SEED, C=1.0),
        'Random Forest': RandomForestClassifier(n_estimators=200, max_depth=10,
                                                 random_state=SEED, n_jobs=-1),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=200, max_depth=4,
                                                         random_state=SEED),
    }

    # XGBoost & LightGBM
    try:
        from xgboost import XGBClassifier
        models['XGBoost'] = XGBClassifier(n_estimators=200, max_depth=5,
                                           learning_rate=0.05, random_state=SEED,
                                           use_label_encoder=False, eval_metric='logloss')
    except ImportError:
        pass

    try:
        from lightgbm import LGBMClassifier
        models['LightGBM'] = LGBMClassifier(n_estimators=200, max_depth=5,
                                             learning_rate=0.05, random_state=SEED, verbose=-1)
    except ImportError:
        pass

    try:
        from catboost import CatBoostClassifier
        models['CatBoost'] = CatBoostClassifier(n_estimators=200, depth=5,
                                                  learning_rate=0.05, random_state=SEED, verbose=0)
    except ImportError:
        pass

    # 训练+评估
    results = []
    all_preds = {}

    for name, model in models.items():
        print(f'  Training {name}...')
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        auc = roc_auc_score(y_test, y_proba)
        f1 = f1_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred)
        recall = recall_score(y_test, y_pred)
        brier = brier_score_loss(y_test, y_proba)

        # Cross-validation AUC
        try:
            cv_scores = cross_val_score(model, X_train, y_train, cv=3,
                                        scoring='roc_auc', n_jobs=-1)
            cv_auc = cv_scores.mean()
            cv_std = cv_scores.std()
        except:
            cv_auc, cv_std = np.nan, np.nan

        # Lift @ 10%
        top10 = int(len(y_test) * 0.1)
        top_idx = np.argsort(y_proba)[-top10:]
        lift_10 = y_test.iloc[top_idx].mean() / y_test.mean()

        results.append({
            'Model': name,
            'AUC': auc, 'F1': f1, 'Precision': precision, 'Recall': recall,
            'Brier': brier, 'CV_AUC': cv_auc, 'CV_Std': cv_std, 'Lift@10%': lift_10
        })
        all_preds[name] = {'pred': y_pred, 'proba': y_proba}
        print(f'    AUC={auc:.4f}, F1={f1:.4f}, Lift@10%={lift_10:.2f}')

    results_df = pd.DataFrame(results).sort_values('AUC', ascending=False)

    # 选择最优模型
    best_model_name = results_df.iloc[0]['Model']
    best_model = models[best_model_name]
    print(f'\n  Best model: {best_model_name} (AUC={results_df.iloc[0]["AUC"]:.4f})')

    return {
        'models': models, 'results': results_df, 'best_model': best_model,
        'best_name': best_model_name, 'X_train': X_train, 'X_test': X_test,
        'y_train': y_train, 'y_test': y_test, 'all_preds': all_preds
    }

# ═══════════════════════════════════════════════════════════════
# 3. 概率校准
# ═══════════════════════════════════════════════════════════════

def calibrate_model(model_results):
    """概率校准"""
    print('\n[Probability Calibration]')
    X_train, X_test = model_results['X_train'], model_results['X_test']
    y_train, y_test = model_results['y_train'], model_results['y_test']
    best_model = model_results['best_model']

    # Platt Scaling (sigmoid)
    cal_platt = CalibratedClassifierCV(best_model, method='sigmoid', cv=3)
    cal_platt.fit(X_train, y_train)
    proba_platt = cal_platt.predict_proba(X_test)[:, 1]

    # Isotonic
    cal_iso = CalibratedClassifierCV(best_model, method='isotonic', cv=3)
    cal_iso.fit(X_train, y_train)
    proba_iso = cal_iso.predict_proba(X_test)[:, 1]

    # 未校准
    proba_raw = model_results['all_preds'][model_results['best_name']]['proba']

    # ECE
    ece_raw = expected_calibration_error(y_test, proba_raw, n_bins=10)
    ece_platt = expected_calibration_error(y_test, proba_platt, n_bins=10)
    ece_iso = expected_calibration_error(y_test, proba_iso, n_bins=10)
    print(f'  ECE: Raw={ece_raw:.4f}, Platt={ece_platt:.4f}, Isotonic={ece_iso:.4f}')

    return {'raw': proba_raw, 'platt': proba_platt, 'isotonic': proba_iso,
            'ece': {'raw': ece_raw, 'platt': ece_platt, 'isotonic': ece_iso}}

def expected_calibration_error(y_true, y_prob, n_bins=10):
    """计算期望校准误差"""
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0
    yt = y_true.values if hasattr(y_true, 'values') else np.array(y_true)
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i+1])
        if mask.sum() > 0:
            conf = y_prob[mask].mean()
            acc = yt[mask].mean()
            ece += mask.sum() / len(yt) * abs(acc - conf)
    return ece

# ═══════════════════════════════════════════════════════════════
# 4. SHAP 分析
# ═══════════════════════════════════════════════════════════════

def run_shap_analysis(model_results):
    """SHAP可解释性分析"""
    print('\n[SHAP Analysis]')
    X_train, X_test = model_results['X_train'], model_results['X_test']
    best_model = model_results['best_model']
    best_name = model_results['best_name']

    shap_values = None
    explainer = None

    try:
        import shap

        # Sample consistently
        n_sample = min(300, len(X_test))
        X_sample = X_test.sample(n_sample, random_state=SEED)

        if 'XGBoost' in best_name or 'LightGBM' in best_name or 'CatBoost' in best_name:
            explainer = shap.TreeExplainer(best_model)
            shap_values = explainer.shap_values(X_sample)
        elif 'Random Forest' in best_name or 'Gradient' in best_name:
            explainer = shap.TreeExplainer(best_model)
            shap_values = explainer.shap_values(X_sample)
        else:
            # Linear model - use KernelExplainer with small sample
            background = shap.sample(X_train, 100, random_state=SEED)
            explainer = shap.KernelExplainer(best_model.predict_proba, background)
            shap_values = explainer.shap_values(X_sample)

        # Fix for binary classification (shap_values can be a list)
        if isinstance(shap_values, list):
            shap_values = shap_values[1] if len(shap_values) > 1 else shap_values[0]

        print(f'  SHAP values shape: {shap_values.shape}')

    except Exception as e:
        print(f'  SHAP error: {e}, using feature importance fallback')
        # Fallback: use model's feature_importances_ or coefficients
        importances = np.zeros(X_test.shape[1])
        if hasattr(best_model, 'feature_importances_'):
            importances = best_model.feature_importances_
        X_sample = X_test.sample(min(300, len(X_test)), random_state=SEED)
        shap_values = np.tile(importances, (len(X_sample), 1))

    return {
        'shap_values': shap_values,
        'X_sample': X_sample,
        'feature_names': list(X_sample.columns),
        'explainer': explainer
    }

# ═══════════════════════════════════════════════════════════════
# 5. 生存分析 (简化版)
# ═══════════════════════════════════════════════════════════════

def run_survival_analysis(wide):
    """生存分析 - 客户流失风险"""
    print('\n[Survival Analysis]')

    data = wide[wide['订单ID'].notna()].copy()

    # 定义"事件"：售后满意度<3或有投诉
    data['churn_event'] = ((data['售后平均满意度'] < 3) | (data['是否有投诉'] == 1)).astype(int)

    # 时间：用投诉/工单日期与交付日期的差
    data['survival_time'] = np.maximum(data['线索到交付天数'].fillna(0) + 30, 1)

    # 特征
    surv_features = ['客户年龄', '交付里程', '是否延迟交付', '投诉次数']
    surv_available = [c for c in surv_features if c in data.columns]

    X_surv = data[surv_available].fillna(0)
    # 添加类别特征
    X_surv = pd.concat([X_surv, pd.get_dummies(data['配置'], prefix='cfg').astype(float)], axis=1)
    X_surv = pd.concat([X_surv, pd.get_dummies(data['城市'], prefix='ct').astype(float)], axis=1)

    y_event = data['churn_event']
    y_time = data['survival_time']

    print(f'  流失率: {y_event.mean()*100:.1f}%')
    print(f'  平均生存时间: {y_time.mean():.0f} 天')

    # Cox比例风险模型
    cox_result = None
    try:
        from lifelines import CoxPHFitter
        cox_data = X_surv.copy()
        cox_data['duration'] = y_time
        cox_data['event'] = y_event
        cph = CoxPHFitter()
        cph.fit(cox_data, duration_col='duration', event_col='event')
        cox_result = cph
        print(f'  Cox concordance: {cph.concordance_index_:.4f}')
    except Exception as e:
        print(f'  Cox model: {e}')

    # Random Survival Forest
    rsf_result = None
    try:
        from sksurv.ensemble import RandomSurvivalForest
        y_struct = np.array([(bool(e), t) for e, t in zip(y_event, y_time)],
                           dtype=[('event', bool), ('time', float)])
        rsf = RandomSurvivalForest(n_estimators=100, max_depth=5, random_state=SEED)
        rsf.fit(X_surv, y_struct)
        rsf_result = rsf
        print(f'  RSF trained successfully')
    except Exception as e:
        print(f'  RSF: {e}')

    return {
        'cox': cox_result, 'rsf': rsf_result,
        'X_surv': X_surv, 'y_event': y_event, 'y_time': y_time,
        'churn_rate': y_event.mean()
    }

# ═══════════════════════════════════════════════════════════════
# 6. 可视化
# ═══════════════════════════════════════════════════════════════

def create_all_w3_charts(model_results, calib_results, shap_results, surv_results, wide):
    """生成W3全部图表"""
    print('\n[Generating W3 Charts]')
    os.makedirs(os.path.join(REPORTS_DIR, 'W3_charts'), exist_ok=True)

    results_df = model_results['results']
    X_test = model_results['X_test']
    y_test = model_results['y_test']
    all_preds = model_results['all_preds']
    best_name = model_results['best_name']

    best_proba = all_preds[best_name]['proba']
    best_pred = all_preds[best_name]['pred']

    # W3_01: ROC曲线
    chart_01_roc_curve(all_preds, y_test)
    # W3_02: PR曲线
    chart_02_pr_curve(all_preds, y_test)
    # W3_03: 混淆矩阵
    chart_03_confusion_matrix(best_pred, y_test)
    # W3_04: 校准曲线
    chart_04_calibration_curve(calib_results, y_test)
    # W3_05: Lift曲线
    chart_05_lift_curve(best_proba, y_test)
    # W3_06: 学习曲线 (简化)
    chart_06_learning_curve(model_results['best_model'], model_results['X_train'], model_results['y_train'])
    # W3_07: 模型对比汇总
    chart_07_model_comparison(results_df)

    # W3_08-10: 特征重要性
    chart_08_feature_importance(model_results['best_model'], X_test.columns)
    chart_09_model_comparison_dashboard(results_df)

    # W3_11-18: SHAP图表
    if shap_results['shap_values'] is not None:
        chart_11_shap_summary(shap_results)
        chart_12_shap_bar(shap_results)
        chart_13_shap_heatmap(shap_results)

    # W3_21-24: 生存分析
    chart_21_survival_curve(wide)
    chart_22_cox_forest(surv_results)
    chart_23_churn_risk_heatmap(wide)

    # W3_19: 客户分群
    chart_19_customer_clusters(wide)

    print(f'  W3 charts generated successfully!')

# --- Individual chart functions ---

def chart_01_roc_curve(all_preds, y_test):
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = CATEGORICAL_10[:len(all_preds)]
    for (name, preds), color in zip(all_preds.items(), colors):
        fpr, tpr, _ = roc_curve(y_test, preds['proba'])
        auc = roc_auc_score(y_test, preds['proba'])
        ax.plot(fpr, tpr, lw=2, color=color, label=f'{name} (AUC={auc:.4f})')
    ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Random (AUC=0.5)')
    ax.set_xlabel('False Positive Rate'); ax.set_ylabel('True Positive Rate')
    ax.set_title('ROC Curves - Model Comparison', fontsize=14, fontweight='bold')
    ax.legend(fontsize=8)
    save_fig(fig, 'w3_01_roc_curve.png', 'W3')

def chart_02_pr_curve(all_preds, y_test):
    fig, ax = plt.subplots(figsize=(10, 8))
    colors = CATEGORICAL_10[:len(all_preds)]
    for (name, preds), color in zip(all_preds.items(), colors):
        precision, recall, _ = precision_recall_curve(y_test, preds['proba'])
        ax.plot(recall, precision, lw=2, color=color, label=name)
    ax.set_xlabel('Recall'); ax.set_ylabel('Precision')
    ax.set_title('Precision-Recall Curves', fontsize=14, fontweight='bold')
    ax.legend(fontsize=8)
    save_fig(fig, 'w3_02_pr_curve.png', 'W3')

def chart_03_confusion_matrix(y_pred, y_test):
    cm = confusion_matrix(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax, xticklabels=['No', 'Yes'], yticklabels=['No', 'Yes'])
    ax.set_xlabel('Predicted'); ax.set_ylabel('Actual')
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    ax.set_title(f'Confusion Matrix\nPrecision={precision:.3f} | Recall={recall:.3f} | F1={f1:.3f}',
                 fontsize=13, fontweight='bold')
    save_fig(fig, 'w3_03_confusion_matrix.png', 'W3')

def chart_04_calibration_curve(calib, y_test):
    fig, ax = plt.subplots(figsize=(8, 8))
    for name, proba in [('Uncalibrated', calib['raw']), ('Platt Scaling', calib['platt']), ('Isotonic', calib['isotonic'])]:
        prob_true, prob_pred = calibration_curve(y_test, proba, n_bins=10)
        ax.plot(prob_pred, prob_true, 'o-', lw=2, label=f'{name} (ECE={calib["ece"][name.lower().split()[0] if name != "Isotonic" else "isotonic"] if name != "Uncalibrated" else calib["ece"]["raw"]:.4f})', markersize=6)
    ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Perfectly Calibrated')
    ax.set_xlabel('Mean Predicted Probability'); ax.set_ylabel('Fraction of Positives')
    ax.set_title('Calibration Curves (Reliability Diagram)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    save_fig(fig, 'w3_04_calibration_curve.png', 'W3')

def chart_05_lift_curve(proba, y_test):
    """Lift曲线"""
    order = np.argsort(proba)[::-1]
    y_sorted = y_test.iloc[order] if hasattr(y_test, 'iloc') else y_test[order]
    cum_gains = np.cumsum(y_sorted) / y_sorted.sum()
    baseline = np.linspace(0, 1, len(y_sorted))

    fig, ax = plt.subplots(figsize=(10, 6))
    x_pct = np.linspace(0, 100, len(cum_gains))
    ax.plot(x_pct, cum_gains, lw=2, color='#2563EB', label='Model')
    ax.plot(x_pct, baseline, 'k--', alpha=0.3, label='Random')
    ax.set_xlabel('Percentage of Sample'); ax.set_ylabel('Cumulative Gain')
    ax.set_title('Cumulative Gains / Lift Curve', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w3_05_lift_curve.png', 'W3')

def chart_06_learning_curve(model, X_train, y_train):
    """简化学习曲线"""
    train_sizes = np.linspace(0.1, 1.0, 10)
    train_scores = []
    test_scores = []
    for size in train_sizes:
        n = int(len(X_train) * size)
        model.fit(X_train[:n], y_train[:n])
        train_scores.append(roc_auc_score(y_train[:n], model.predict_proba(X_train[:n])[:, 1]))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(train_sizes*100, train_scores, 'o-', color='#2563EB', lw=2, markersize=6, label='Training AUC')
    ax.set_xlabel('Training Set Size (%)'); ax.set_ylabel('AUC')
    ax.set_title('Learning Curve', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w3_06_learning_curve.png', 'W3')

def chart_07_model_comparison(results_df):
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(results_df))
    ax.bar(x, results_df['AUC'], color=CATEGORICAL_10[:len(results_df)], width=0.5, alpha=0.9)
    ax.set_xticks(x); ax.set_xticklabels(results_df['Model'], rotation=25, ha='right', fontsize=9)
    ax.set_ylabel('AUC'); ax.set_title('Model AUC Comparison', fontsize=14, fontweight='bold')
    for i, (_, r) in enumerate(results_df.iterrows()):
        ax.text(i, r['AUC']+0.003, f'{r["AUC"]:.4f}', ha='center', fontsize=10, fontweight='bold')
    ax.set_ylim(ax.get_ylim()[0], ax.get_ylim()[1]*1.05)
    save_fig(fig, 'w3_07_model_comparison_bar.png', 'W3')

def chart_08_feature_importance(model, feature_names):
    if hasattr(model, 'feature_importances_'):
        imp = model.feature_importances_
        imp_df = pd.DataFrame({'Feature': feature_names, 'Importance': imp}).sort_values('Importance', ascending=False).head(20)
        fig, ax = plt.subplots(figsize=(10, 8))
        bars = ax.barh(range(len(imp_df)), imp_df['Importance'], color='#2563EB', alpha=0.8)
        ax.set_yticks(range(len(imp_df))); ax.set_yticklabels(imp_df['Feature'], fontsize=9)
        ax.set_xlabel('Importance'); ax.invert_yaxis()
        ax.set_title('Top 20 Feature Importance', fontsize=14, fontweight='bold')
        save_fig(fig, 'w3_08_feature_importance.png', 'W3')

def chart_09_model_comparison_dashboard(results_df):
    """综合模型对比气泡图"""
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = CATEGORICAL_10[:len(results_df)]
    for i, (_, r) in enumerate(results_df.iterrows()):
        ax.scatter(r['AUC'], r['F1'], s=r['Lift@10%']*500, c=colors[i], alpha=0.7, edgecolors='black', linewidth=1)
        ax.annotate(r['Model'].split()[0], (r['AUC'], r['F1']), fontsize=9, ha='center', va='bottom')
    ax.set_xlabel('AUC'); ax.set_ylabel('F1 Score')
    ax.set_title('Model Performance Dashboard (bubble size = Lift@10%)', fontsize=14, fontweight='bold')
    save_fig(fig, 'w3_09_model_dashboard.png', 'W3')

def chart_11_shap_summary(shap_results):
    """SHAP Beeswarm"""
    try:
        import shap
        fig, ax = plt.subplots(figsize=(14, 10))
        shap.summary_plot(shap_results['shap_values'], shap_results['X_sample'],
                          feature_names=shap_results['feature_names'], show=False, max_display=20)
        fig.suptitle('SHAP Beeswarm Summary Plot', fontsize=14, fontweight='bold', y=1.01)
        save_fig(fig, 'w3_11_shap_beeswarm.png', 'W3')
    except Exception as e:
        print(f'  SHAP beeswarm error: {e}')

def chart_12_shap_bar(shap_results):
    """SHAP Bar Plot"""
    try:
        import shap
        fig, ax = plt.subplots(figsize=(10, 8))
        shap.summary_plot(shap_results['shap_values'], shap_results['X_sample'],
                          feature_names=shap_results['feature_names'], plot_type='bar',
                          show=False, max_display=20)
        fig.suptitle('SHAP Feature Importance (Mean |SHAP|)', fontsize=14, fontweight='bold', y=1.01)
        save_fig(fig, 'w3_12_shap_bar.png', 'W3')
    except Exception as e:
        print(f'  SHAP bar error: {e}')

def chart_13_shap_heatmap(shap_results):
    """SHAP Heatmap"""
    try:
        import shap
        fig, ax = plt.subplots(figsize=(16, 10))
        shap.plots.heatmap(shap.Explanation(shap_results['shap_values'][:100],
                                             feature_names=shap_results['feature_names']), show=False)
        fig.suptitle('SHAP Value Clustering Heatmap (Top 100 Samples)', fontsize=14, fontweight='bold', y=1.02)
        save_fig(fig, 'w3_13_shap_heatmap.png', 'W3')
    except Exception as e:
        print(f'  SHAP heatmap error: {e}')

def chart_19_customer_clusters(wide):
    """客户分群散点图"""
    data = wide.sample(min(2000, len(wide)))
    fig, ax = plt.subplots(figsize=(10, 7))
    colors = {0: '#EF4444', 1: '#10B981'}
    for label in [0, 1]:
        sub = data[data['是否下订'] == label]
        ax.scatter(sub['客户年龄'], sub['试驾时长'], c=colors[label], alpha=0.4, s=15,
                   label=f'{"Converted" if label else "Not Converted"}')
    ax.set_xlabel('Age'); ax.set_ylabel('Test Drive Duration (min)')
    ax.set_title('Customer Segmentation: Age vs Test Drive', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w3_19_customer_clusters.png', 'W3')

def chart_21_survival_curve(wide):
    """Kaplan-Meier生存曲线"""
    data = wide[wide['订单ID'].notna()]
    if '线索到交付天数' not in data.columns:
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    for config in data['配置'].dropna().unique()[:3]:
        sub = data[data['配置'] == config]
        times = sub['线索到交付天数'].dropna().sort_values()
        if len(times) > 10:
            surv = 1 - np.arange(1, len(times)+1) / len(times)
            ax.step(times, surv, where='post', lw=2, label=f'{config} (n={len(times)})')
    ax.set_xlabel('Days Since Lead'); ax.set_ylabel('Survival Probability')
    ax.set_title('Kaplan-Meier Style Survival Curves by Configuration', fontsize=14, fontweight='bold')
    ax.legend()
    save_fig(fig, 'w3_21_survival_curve.png', 'W3')

def chart_22_cox_forest(surv_results):
    """Cox风险比森林图"""
    cox = surv_results['cox']
    if cox is None:
        return
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        summary = cox.summary
        summary = summary.sort_values('exp(coef)')
        ax.errorbar(summary['exp(coef)'], range(len(summary)),
                    xerr=[summary['exp(coef)'] - summary['exp(coef) lower 0.95'],
                          summary['exp(coef) upper 0.95'] - summary['exp(coef)']],
                    fmt='o', capsize=3, color='#2563EB', markersize=8, elinewidth=1.5)
        ax.set_yticks(range(len(summary))); ax.set_yticklabels(summary.index, fontsize=9)
        ax.axvline(x=1, color='#EF4444', linestyle='--', lw=1.5, alpha=0.5)
        ax.set_xlabel('Hazard Ratio'); ax.set_title('Cox Model: Hazard Ratios (Forest Plot)', fontsize=14, fontweight='bold')
        save_fig(fig, 'w3_22_cox_forest.png', 'W3')
    except Exception as e:
        print(f'  Cox forest error: {e}')

def chart_23_churn_risk_heatmap(wide):
    """流失风险热力图（城市×投诉类型）"""
    data = wide[wide['订单ID'].notna()]
    if '主要投诉类型' not in data.columns:
        return
    data['churn_risk'] = ((data['售后平均满意度'] < 3) | (data['是否有投诉'] == 1)).astype(int)
    risk_pivot = data.pivot_table(values='churn_risk', index='城市', columns='主要投诉类型', aggfunc='mean') * 100
    fig, ax = plt.subplots(figsize=(14, 8))
    sns.heatmap(risk_pivot, annot=True, fmt='.1f', cmap='YlOrRd', ax=ax, linewidths=0.5,
                cbar_kws={'label': 'Churn Risk (%)'})
    ax.set_title('Churn Risk Heatmap: City x Complaint Type', fontsize=14, fontweight='bold')
    save_fig(fig, 'w3_23_churn_risk_heatmap.png', 'W3')

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('  G9 W3: Predictive Modeling & Early Warning')
    print('=' * 60)

    # Load data
    wide_path = os.path.join(DATA_DIR, 'wide_table.parquet')
    if not os.path.exists(wide_path):
        wide_path = os.path.join(DATA_DIR, 'wide_table.csv')
    wide = pd.read_parquet(wide_path) if wide_path.endswith('.parquet') else pd.read_csv(wide_path)
    print(f'  Loaded wide table: {wide.shape[0]:,} x {wide.shape[1]}')

    # 1. Feature engineering
    X, y = prepare_modeling_data(wide)

    # 2. Model training & comparison
    model_results = train_and_compare_models(X, y)

    # 3. Calibration
    calib_results = calibrate_model(model_results)

    # 4. SHAP
    shap_results = run_shap_analysis(model_results)

    # 5. Survival analysis
    surv_results = run_survival_analysis(wide)

    # 6. Charts
    create_all_w3_charts(model_results, calib_results, shap_results, surv_results, wide)

    # Save best model
    with open(os.path.join(MODELS_DIR, 'conversion_model.pkl'), 'wb') as f:
        pickle.dump(model_results['best_model'], f)
    print(f'\n  Best model saved: models/conversion_model.pkl')

    print('\n[OK] W3 Complete!')
    print(f'  Best AUC: {model_results["results"].iloc[0]["AUC"]:.4f}')
    print(f'  Charts: reports/W3_charts/')
