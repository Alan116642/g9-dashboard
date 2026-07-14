# G9 智能销售运营决策

这是一个以审计后数据和统一证据接口驱动的 Streamlit 销售运营看板。原始 Excel 保持只读；本地流程重建线索级、订单级和跟进事件级数据，并把审核后的分析结果写入 `analysis_results.json`。

线上地址：[G9 智能销售运营决策](https://aopdxrkem3gdhpsqqbxuzy.streamlit.app/)

## 六个页面

六个页面合计提供 40 张交互式分析图；W5 白皮书同步提供 40 张经审计的静态分析图，并为每张图附上口径或证据边界说明。

图表使用统一行动语义色：红色“优先改进”、橙色“需要关注”、绿色“表现较好”、蓝灰色“描述性/不可判优劣”。红橙绿按当前图表范围内的相对分位生成，不代表业务目标、统计显著性或因果效应；图例文字同时提供非颜色识别。

- 运营全景：统一展示线索、下订、转化、有效订单、延迟和评分口径。
- 渠道分析：展示渠道规模、每百线索订单数和标准化边际转化率；不把单渠道数据包装为多触点归因。
- 预测中心：按时间顺序验证基线模型；公开模式关闭逐客户预测。
- 风险预警：只展示城市—月份聚合风险，不公开客户明细。
- 销售团队：只统计销售人员入职后且不晚于交付的有效跟进。
- 策略推荐：根据证据等级和置信区间生成，并把证据不足的动作标为需补数或实验验证。

## 数据模式

- 本地模式优先读取 `data/processed/` 的完整派生汇总，并标记“本地完整数据”。
- 公开模式只读取 `data_demo/` 的脱敏汇总，并标记“公开脱敏汇总数据”。
- 公开单元的月份、城市、渠道、性别、年龄段组合若样本量小于 10，则不发布该单元。
- 原始 Excel、真实逐行 CSV、模型和客户/销售人员标识不会提交到 GitHub。

公开仓库只包含：

- `data_demo/dashboard_lead_cube.csv`
- `data_demo/dashboard_order_cube.csv`
- `data_demo/analysis_results.json`
- `data_demo/dashboard_metadata.json`
- `data_demo/W4_strategy_comparison.csv`

## 本地运行

```powershell
python -m pip install -r requirements.txt
$env:APP_PASSWORD = "your-local-password"
python -m streamlit run dashboard/app.py
```

看板没有硬编码密码。Streamlit Cloud 必须在应用 Secrets 中配置：

```toml
APP_PASSWORD = "use-a-strong-random-secret"
```

缺少该配置时，应用会显示配置错误，不会回退到默认密码。

## 重建完整分析

完整分析依赖见 `requirements-analysis.txt`。将原始工作簿保留在项目根目录后运行：

```powershell
python -m pip install -r requirements-analysis.txt
python run.py all
```

流程会依次重建数据质量审计、因果/关联分析、时间外预测、机会排序、图表、Notebook、DOCX、PDF 和看板数据。原始工作簿不会被写入。

## 关键证据边界

- 面谈分析使用基线协变量倾向得分匹配、共同支持、卡钳、城市/月份精确约束和 AIPW 稳健性验证。缺少下订时间戳，因此只能在时序假设成立时解释。
- 交付延迟只对无关键字段冲突订单报告调整后关联。缺少承诺/实际交付时间和完整混杂变量，不能表述为严格因果效应。
- 数据没有合法连续分配变量和业务阈值，因此 RDD 被识别审计阻止。
- 每条线索只有一个获客渠道，且费用只有城市—月份总额，因此不计算多触点 Shapley、渠道 ROI 或 CPO。

所有页面、图表和报告均从同一结果接口读取估计、标准误、95% 置信区间、样本量、方法、平衡状态、假设、证据等级和数据截止日期。
