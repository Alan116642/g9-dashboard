"""G9 pipeline entry point.

Usage: python run.py [w1|w2|w3|w4|w5|all]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the G9 audited analytics pipeline")
    parser.add_argument("target", choices=["w1", "w2", "w3", "w4", "w5", "all"])
    args = parser.parse_args()

    if args.target == "all":
        from g9_pipeline import run_all_core
        from reporting import generate_all_reports
        bundle, results, charts = run_all_core()
        generate_all_reports(bundle, results, charts)
        print("All G9 stages completed successfully.")
        return

    module = __import__({
        "w1": "w1_cleaning",
        "w2": "w2_causal",
        "w3": "w3_modeling",
        "w4": "w4_optimization",
        "w5": "w5_generate",
    }[args.target])
    module.main()


if __name__ == "__main__":
    main()
