# G9 智能销售运营决策系统

数据驱动 · 全链路优化 · Streamlit 密码保护仪表盘

## 在线部署到 Streamlit Cloud

1. 打开 https://streamlit.io/cloud
2. 使用 GitHub 账号登录
3. 点击 `New app`
4. 选择仓库：`Alan116642/g9-dashboard`
5. 选择分支：`main`
6. Main file path 填写：`dashboard/app.py`
7. 点击 `Deploy`

访问密码：`040102`

仓库内包含 `data_demo/wide_table.csv` 合成演示数据，因此可以直接部署运行。真实业务数据不会上传到 GitHub。

## 本地运行真实数据

```bash
git clone https://github.com/Alan116642/g9-dashboard.git
cd g9-dashboard
pip install -r requirements.txt

# 放入真实数据文件
mkdir data
# 将 wide_table.csv 放到 data/wide_table.csv

python -m streamlit run dashboard/app.py
```

仪表盘会优先读取 `data/wide_table.csv`。如果本地没有真实数据，会自动读取 `data_demo/wide_table.csv`。

## 项目结构

```text
g9-dashboard/
├── dashboard/app.py              # Streamlit 交互仪表盘
├── data_demo/                    # 可公开的合成演示数据
│   ├── wide_table.csv
│   └── W4_strategy_comparison.csv
├── src/                          # 数据清洗、建模、因果分析、优化脚本
├── requirements.txt
├── run.py
└── .gitignore
```

## 数据安全

- `data/`、`models/`、`reports/`、`catboost_info/` 已通过 `.gitignore` 排除。
- GitHub 仓库只上传代码和合成 demo 数据。
- 真实 Excel、CSV、模型文件、报告文件不会推送到 GitHub。
- 仪表盘密码是基础访问门禁，不适合作为高安全级别认证。
