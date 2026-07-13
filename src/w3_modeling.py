"""W3: chronological conversion-risk model using baseline-only features."""
from g9_pipeline import build_clean_data, run_conversion_model


def main():
    bundle = build_clean_data(save=True)
    result, importance = run_conversion_model(bundle.leads)
    print(f"W3 complete: out-of-time ROC AUC={result['metrics']['roc_auc']:.3f}")
    return result, importance


if __name__ == "__main__":
    main()
