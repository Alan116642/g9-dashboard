"""Fail CI when tracked/public files expose row-level data, secrets, or retired claims."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data_demo"
ALLOWED_PUBLIC = {
    "dashboard_lead_cube.csv",
    "dashboard_order_cube.csv",
    "W4_strategy_comparison.csv",
    "analysis_results.json",
    "dashboard_metadata.json",
}
FORBIDDEN_COLUMNS = {"线索ID", "订单ID", "销售员ID", "手机号", "姓名", "客户姓名", "精确日期"}
FORBIDDEN_TEXT = [
    "04" + "0102",
    "面谈" + "+4pp",
    "显著" + "降低评分",
    "渠道 " + "Shapley ROI",
]
SECRET_MARKERS = ["AK" + "IA", "BEGIN " + "PRIVATE KEY"]


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8")
    return [ROOT / line for line in output.splitlines() if line]


def main() -> None:
    errors: list[str] = []
    public_files = {p.name for p in PUBLIC.iterdir() if p.is_file() and not p.name.startswith(".")}
    extra = public_files - ALLOWED_PUBLIC
    if extra:
        errors.append(f"Unapproved public files: {sorted(extra)}")

    for path in PUBLIC.glob("*.csv"):
        frame = pd.read_csv(path)
        exposed = FORBIDDEN_COLUMNS.intersection(frame.columns)
        if exposed:
            errors.append(f"{path.name}: exposed columns {sorted(exposed)}")
        count_candidates = [c for c in frame.columns if c in {"线索数", "有效订单数"}]
        for col in count_candidates:
            if not frame.empty and (frame[col] < 10).any():
                errors.append(f"{path.name}: {col} contains a cell below suppression threshold")

    metadata = json.loads((PUBLIC / "dashboard_metadata.json").read_text(encoding="utf-8"))
    if metadata.get("privacy", {}).get("cell_suppression_threshold") != 10:
        errors.append("Public suppression threshold must equal 10")

    text_suffixes = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt"}
    for path in tracked_files():
        if path.suffix.lower() not in text_suffixes or not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for phrase in FORBIDDEN_TEXT + SECRET_MARKERS:
            if phrase in content:
                errors.append(f"{path.relative_to(ROOT)} contains forbidden text marker")

    if errors:
        raise SystemExit("\n".join(errors))
    print("Public-data and secret scan passed.")


if __name__ == "__main__":
    main()
