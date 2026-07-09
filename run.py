"""
G9 项目启动脚本 — 设置UTF-8编码
用法: python run.py w1 (运行W1) 或 python run.py all (运行全部)
"""
import sys
import os
import io

# Force UTF-8 encoding for stdout/stderr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python run.py [w1|w2|w3|w4|w5|all]")
        sys.exit(1)

    target = sys.argv[1].lower()

    if target in ('w1', 'all'):
        print("\n" + "="*60)
        print("  Running W1: Data Cleaning & Wide Table")
        print("="*60)
        import w1_cleaning
        # Main is auto-executed on import; if not, call it
        if hasattr(w1_cleaning, '__name__'):
            pass  # Already ran

    if target in ('w2', 'all'):
        print("\n" + "="*60)
        print("  Running W2: Causal Inference & Attribution")
        print("="*60)
        import w2_causal

    if target in ('w3', 'all'):
        print("\n" + "="*60)
        print("  Running W3: Predictive Modeling")
        print("="*60)
        import w3_modeling

    if target in ('w4', 'all'):
        print("\n" + "="*60)
        print("  Running W4: Strategy Optimization")
        print("="*60)
        import w4_optimization

    if target in ('w5', 'all'):
        print("\n" + "="*60)
        print("  Running W5: Dashboard")
        print("="*60)
        print("  Run: streamlit run dashboard/app.py")

    print("\nDone!")
