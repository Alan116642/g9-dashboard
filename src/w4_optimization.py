"""W4: opportunity prioritization; channel ROI/CPO are intentionally not estimated."""
from g9_pipeline import build_clean_data, run_analysis


def main():
    bundle = build_clean_data(save=True)
    results, charts = run_analysis(bundle)
    strategy = charts["strategy"]
    print(f"W4 complete: {len(strategy):,} city-channel opportunities ranked")
    return strategy


if __name__ == "__main__":
    main()
