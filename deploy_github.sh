#!/bin/bash
# G9 仪表盘 GitHub 部署脚本
# 运行前请先在 GitHub 创建空仓库: https://github.com/new
# 然后填写下面的仓库地址

GITHUB_REPO="https://github.com/你的用户名/g9-dashboard.git"
# ↑↑↑ 请修改为你的GitHub仓库地址 ↑↑↑

echo "============================================"
echo "  G9 仪表盘 GitHub 部署"
echo "============================================"

# 1. 配置 git
git config user.name "G9-Analytics"
git config user.email "g9@analytics.dev"

# 2. 只提交代码文件(数据已排除)
git add dashboard/ src/ requirements.txt .gitignore run.py
git rm --cached -r data/ models/ reports/ catboost_info/ .claude/ 2>/dev/null

# 3. 提交
git commit -m "G9智能销售运营决策系统 v2.0 - 密码保护仪表盘

- 6 Tab全交互Streamlit仪表盘
- 密码验证: 040102
- 数据诊断+因果推断+预测建模+策略优化
- 68张可视化图表
- 5份Word分析报告(代码)
- 数据文件已排除(.gitignore)"

# 4. 推送
git remote remove origin 2>/dev/null
git remote add origin "$GITHUB_REPO"
git branch -M main
git push -u origin main

echo ""
echo "[OK] 代码已推送到 GitHub!"
echo "数据文件(含敏感信息)未上传, 符合安全要求。"
echo ""
echo "===== 使用说明 ====="
echo "1. 克隆: git clone $GITHUB_REPO"
echo "2. 安装: pip install -r requirements.txt"
echo "3. 放入数据文件到 data/wide_table.csv"
echo "4. 运行: python -m streamlit run dashboard/app.py"
echo "5. 密码: 040102"
