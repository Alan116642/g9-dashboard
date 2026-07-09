# G9 智能销售运营决策系统

> 数据驱动 · 全链路优化 · Q4销量增长15%目标

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 放入数据文件
# 将 wide_table.csv 放入 data/ 目录

# 3. 启动仪表盘
python -m streamlit run dashboard/app.py

# 4. 浏览器访问 http://localhost:8501
# 密码: 040102
```

## 密码保护

仪表盘启动后需要输入密码才能访问：**040102**

密码使用 SHA256 哈希比对，不在代码中明文存储。

## 项目结构

```
G9/
├── dashboard/app.py          # Streamlit 交互仪表盘 (6 Tab, 密码保护)
├── src/
│   ├── config.py             # 全局配置 + 可视化样式
│   ├── utils.py              # 公共工具函数
│   ├── w1_cleaning.py        # W1: 数据清洗 + 宽表构建
│   ├── w2_causal.py          # W2: PSM/RDD/IV/HTE 因果推断
│   ├── w3_modeling.py        # W3: LightGBM + SHAP + 生存分析
│   ├── w4_optimization.py    # W4: LP/GA/博弈论/TOPSIS 优化
│   ├── w5_generate.py        # W5: 白皮书 + PPT
│   └── generate_reports.py   # Word 报告生成器
├── data/                     # 数据文件 (gitignore 排除)
├── reports/                  # 分析报告 (gitignore 排除)
├── models/                   # 训练模型 (gitignore 排除)
├── requirements.txt
└── .gitignore
```

## 仪表盘功能

| Tab | 内容 |
|-----|------|
| 📊 运营全景 | KPI卡片、月度趋势、城市矩阵、转化漏斗、每日趋势 |
| 📡 渠道分析 | 转化排名、份额环形图、ROI、热力图、综合指标表 |
| 🤖 预测中心 | 客户特征输入→实时转化概率预测 |
| ⚠️ 风险预警 | 风险分层、投诉分析、高风险客户CSV导出 |
| 👥 销售团队 | Top销售员排名、转化vs处理量散点 |
| 📋 策略推荐 | TOPSIS评分、四大策略详情卡片 |

## 技术栈

- **数据处理**: Pandas, NumPy
- **因果推断**: PSM, RDD, IV, Shapley Value
- **建模**: LightGBM, XGBoost, CatBoost, Optuna
- **可解释性**: SHAP
- **优化**: 线性规划, 遗传算法, 博弈论, TOPSIS
- **可视化**: Plotly, Matplotlib, Seaborn
- **仪表盘**: Streamlit
- **报告**: python-docx, python-pptx

## 数据安全

- 所有数据仅本地处理，不外传
- `data/`、`models/`、`reports/` 已通过 `.gitignore` 排除
- GitHub 仓库仅包含源代码和仪表盘，不含任何业务数据
- 密码使用 SHA256 哈希验证
