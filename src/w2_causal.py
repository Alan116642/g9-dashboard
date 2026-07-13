"""W2: run the audited causal-attribution and adjusted-association workflow."""
from g9_pipeline import build_clean_data, run_analysis


def main():
    bundle = build_clean_data(save=True)
    results, charts = run_analysis(bundle)
    att = results["psm"]["psm_att"]
    print(f"W2 complete: ATT={att['estimate']:.6f}, CI={att['ci95']}, balance={att['balance_status']}")
    return results, charts


if __name__ == "__main__":
    main()
