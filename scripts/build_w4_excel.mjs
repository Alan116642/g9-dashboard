import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const sourcePath = path.join(root, "data", "processed", "W4_strategy_comparison.csv");
const outputPath = path.join(root, "reports", "W4_策略方案对比表.xlsx");
const previewDir = path.join(root, "tmp", "w4_excel_preview");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

function colName(index) {
  let n = index + 1;
  let out = "";
  while (n) {
    n -= 1;
    out = String.fromCharCode(65 + (n % 26)) + out;
    n = Math.floor(n / 26);
  }
  return out;
}

const csvText = await fs.readFile(sourcePath, "utf8");
const raw = parseCsv(csvText);
const headers = raw[0];
const numericColumns = new Set(["线索数", "订单数", "有效跟进线索数", "有效跟进次数", "转化率", "跟进覆盖率", "机会量", "优先级分"]);
const data = raw.slice(1).filter((r) => r.some((v) => v !== "")).map((row) =>
  row.map((value, i) => (numericColumns.has(headers[i]) ? Number(value) : value)),
);

const workbook = Workbook.create();
const strategy = workbook.worksheets.add("策略对比");
const feasibility = workbook.worksheets.add("方法可行性");
const guide = workbook.worksheets.add("使用说明");

const lastCol = colName(headers.length - 1);
const lastRow = data.length + 1;
strategy.getRange(`A1:${lastCol}${lastRow}`).values = [headers, ...data];
strategy.getRange(`A1:${lastCol}1`).format = {
  fill: "#155E75",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
strategy.getRange(`A2:${lastCol}${lastRow}`).format = {
  font: { color: "#172554" },
  verticalAlignment: "center",
};
strategy.getRange(`E2:F${lastRow}`).format.numberFormat = "0";
strategy.getRange(`G2:H${lastRow}`).format.numberFormat = "0.0%";
strategy.getRange(`I2:J${lastRow}`).format.numberFormat = "0.0";
strategy.getRange(`J2:J${lastRow}`).conditionalFormats.add("colorScale", {
  criteria: [
    { type: "lowestValue", color: "#16A34A" },
    { type: "percentile", value: 50, color: "#FACC15" },
    { type: "highestValue", color: "#DC2626" },
  ],
});
strategy.getRange(`A1:${lastCol}${lastRow}`).format.autofitColumns();
strategy.getRange(`K2:K${lastRow}`).format.wrapText = true;
strategy.getRange("A:A").format.columnWidth = 12;
strategy.getRange("B:B").format.columnWidth = 12;
strategy.getRange("K:K").format.columnWidth = 34;
strategy.freezePanes.freezeRows(1);
strategy.tables.add(`A1:${lastCol}${lastRow}`, true, "StrategyComparisonTable");

strategy.getRange("M1:N1").values = [["城市×渠道", "优先级分"]];
strategy.getRange("M2:N2").formulas = [["=A2&\"·\"&B2", "=J2"]];
strategy.getRange("M2:N11").fillDown();
const chart = strategy.charts.add("bar", strategy.getRange("M1:N11"));
chart.title = "优先改进机会 Top 10";
chart.hasLegend = false;
chart.xAxis = { axisType: "textAxis" };
chart.yAxis = { numberFormatCode: "0.0" };
chart.setPosition("M13", "U31");

feasibility.getRange("A1:D6").values = [
  ["模块", "当前状态", "可交付结果", "仍需补充的数据"],
  ["机会优先级", "已完成", "按线索量、标准化转化差异、跟进覆盖和风险信号排序", "上线后试验结果用于更新权重"],
  ["预算优化", "暂不识别", "不输出渠道预算增减或 ROI", "渠道级花费、边际获客成本、预算上下限"],
  ["定价博弈", "可行性审计", "不生成竞品降价响应数值", "竞品价格、需求弹性、成交价与折扣"],
  ["整数排班", "可行性审计", "仅报告入职后有效跟进和容量线索", "班次、技能、可服务时间和分配约束"],
  ["执行原则", "已锁定", "证据不足时显示需补数据/实验验证", "持续维护数据责任人与口径版本"],
];
feasibility.getRange("A1:D1").format = { fill: "#155E75", font: { bold: true, color: "#FFFFFF" } };
feasibility.getRange("A2:D6").format.wrapText = true;
feasibility.getRange("A1:D6").format.autofitRows();
feasibility.getRange("A:A").format.columnWidth = 18;
feasibility.getRange("B:B").format.columnWidth = 16;
feasibility.getRange("C:C").format.columnWidth = 46;
feasibility.getRange("D:D").format.columnWidth = 42;
feasibility.freezePanes.freezeRows(1);

guide.getRange("A1:B10").values = [
  ["项目", "说明"],
  ["文件定位", "W4 策略方案对比与方法可行性审计"],
  ["数据来源", "data/processed/W4_strategy_comparison.csv"],
  ["数据口径", "城市×渠道聚合，不含客户、订单或销售人员明细 ID"],
  ["优先级分", "用于发现更值得诊断和试验的组合，不等于 ROI 或预算回报"],
  ["颜色规则", "红色=优先改进，黄色=需要关注，绿色=相对稳定"],
  ["预算限制", "当前费用只有城市—月份总额，不能分配到渠道"],
  ["因果限制", "标准化渠道差异仍是关联性结果，不是渠道因果贡献"],
  ["使用建议", "先在 Top 组合开展小规模随机试验，再决定资源调整"],
  ["版本", "2026-07-22 证据审计版"],
];
guide.getRange("A1:B1").format = { fill: "#155E75", font: { bold: true, color: "#FFFFFF" } };
guide.getRange("A2:B10").format.wrapText = true;
guide.getRange("A:A").format.columnWidth = 20;
guide.getRange("B:B").format.columnWidth = 70;
guide.getRange("A1:B10").format.autofitRows();
guide.freezePanes.freezeRows(1);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
for (const sheetName of ["策略对比", "方法可行性", "使用说明"]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
