"""W5: generate reports and machine-readable decision artifacts from one result interface."""
from g9_pipeline import run_all_core
from reporting import generate_all_reports


def main():
    bundle, results, charts = run_all_core()
    artifacts = generate_all_reports(bundle, results, charts)
    print("W5 complete: reports and dashboard artifacts regenerated")
    return artifacts


if __name__ == "__main__":
    main()
