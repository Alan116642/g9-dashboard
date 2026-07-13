"""W1: rebuild audited lead, order, and follow-up event tables."""
from g9_pipeline import build_clean_data


def main():
    bundle = build_clean_data(save=True)
    print(f"W1 complete: {len(bundle.leads):,} leads, {len(bundle.orders):,} unique orders, {len(bundle.followups):,} follow-up events")
    return bundle


if __name__ == "__main__":
    main()
