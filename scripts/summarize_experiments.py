"""Refresh generated CSV/Markdown tables from the registry; metadata only."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video_search.reporting import generate, terminal_table

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', default='experiments/registry.json')
    parser.add_argument('--csv', default='experiments/summary.csv')
    parser.add_argument('--report', default='docs/RESULTS_OVERVIEW.md')
    args = parser.parse_args()
    try:
        rows = generate(ROOT, args.registry, args.csv, args.report)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Cannot summarize experiments: {error}\n')
    print(terminal_table(rows))
    print()
    print(f'Summarized {len(rows)} completed experiment(s). No models/videos/indexes were loaded.')
    print(f'Open {args.report}; CSV: {args.csv}')
