"""List, inspect or run named experiments from configs/experiments.json."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from video_search.experiments import CATALOG, describe, load_catalog, run, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', default=CATALOG)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('list', help='Show method, footage and status for every definition')
    for action in ('show', 'run', 'results'):
        entry = sub.add_parser(action)
        entry.add_argument('--id', required=True, help='experiment_id from the catalog')
        if action == 'run':
            entry.add_argument('--dry-run', action='store_true', help='Show settings/commands without processing or writing files')
    args = parser.parse_args()
    try:
        specs = load_catalog(ROOT, args.catalog)['experiments']
        if args.action == 'list':
            print('EXPERIMENT | METHOD | FOOTAGE | SELECTION SETTINGS | STATUS')
            for spec in specs:
                settings=f"{spec['interval_seconds']} s" if spec['method']=='uniform' else f"{spec['max_frames']} retained frames"
                print(f'{spec["experiment_id"]} | {spec["method"]} + OpenCLIP | {spec["footage"]} | {settings} | {status(ROOT, spec)}')
            return
        spec = next((s for s in specs if s['experiment_id'] == args.id), None)
        if spec is None:
            raise ValueError(f'Unknown experiment ID: {args.id}; use list')
        if args.action == 'results':
            from video_search.reporting import terminal_results
            print(terminal_results(ROOT, args.id))
        elif args.action == 'show' or args.dry_run:
            print(json.dumps(describe(ROOT, spec), indent=2))
        else:
            run(ROOT, spec, args.catalog)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f'Cannot run experiment: {error}\n')


if __name__ == '__main__':
    main()
