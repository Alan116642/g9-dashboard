from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data_demo"


def public_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        h.update(path.name.encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def test_public_cubes_are_aggregated_and_suppressed():
    lead = pd.read_csv(PUBLIC / "dashboard_lead_cube.csv")
    order = pd.read_csv(PUBLIC / "dashboard_order_cube.csv")
    forbidden = {"线索ID", "订单ID", "销售员ID", "姓名", "手机号", "日期", "交付日期"}
    assert not forbidden.intersection(lead.columns)
    assert not forbidden.intersection(order.columns)
    assert (lead["线索数"] >= 10).all()
    assert (order["有效订单数"] >= 10).all()


def test_public_hash_matches_metadata():
    files = [
        PUBLIC / "dashboard_lead_cube.csv",
        PUBLIC / "dashboard_order_cube.csv",
        PUBLIC / "W4_strategy_comparison.csv",
        PUBLIC / "analysis_results.json",
    ]
    metadata = json.loads((PUBLIC / "dashboard_metadata.json").read_text(encoding="utf-8"))
    assert public_hash(files) == metadata["public_data_hash"]
