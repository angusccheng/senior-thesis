"""Command-line entry point; see README.md for reproducible experiments."""
import argparse
import csv
import json
from time import perf_counter
from pathlib import Path

from video_search.encoder import MODEL_NAME, PRETRAINED, OpenCLIPEncoder
from video_search.pipeline import build_index, export_previews, load_index, search_index, sha256_file
from video_search.samplers import UniformSampler, DiversitySampler


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def format_time(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    seconds, millis = divmod(millis, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}'


def main():
    parser = argparse.ArgumentParser(description='Modular natural-language frame retrieval')
    sub = parser.add_subparsers(dest='command', required=True)
    index = sub.add_parser('index', help='Select frames and build an index')
    index.add_argument('--video', required=True, type=Path)
    index.add_argument('--method', choices=['uniform', 'diversity'], default='uniform')
    index.add_argument('--interval', type=float, default=5)
    index.add_argument('--max-frames', type=positive_int)
    index.add_argument('--batch-size', type=positive_int, default=16)
    index.add_argument('--model', default=MODEL_NAME)
    index.add_argument('--pretrained', default=PRETRAINED)
    index.add_argument('--dataset-manifest', type=Path, help='Optional shared availability and source-timeline manifest')
    search = sub.add_parser('search', help='Search an existing index')
    search.add_argument('--query', required=True)
    search.add_argument('--top-k', type=positive_int, default=5)
    search.add_argument('--output', type=Path, default=Path('output/matches'))
    search.add_argument('--video', type=Path, help='Relocated source video for previews')
    search.add_argument('--no-previews', action='store_true', help='Retrieve without source-video access')
    for command in (index, search):
        command.add_argument('--index', type=Path, default=Path('output/index.npz'))
        command.add_argument('--device', default='cpu', choices=['cpu', 'cuda', 'mps'])
        command.add_argument('--threads', type=positive_int, default=4)
        command.add_argument('--cache-dir', type=Path, default=Path('.cache/open_clip'))
    args = parser.parse_args()
    try:
        if args.command == 'index':
            if args.method == 'diversity' and args.max_frames is None:
                raise ValueError('Diversity sampling requires --max-frames')
            sampler = (DiversitySampler(args.max_frames) if args.method == 'diversity'
                       else UniformSampler(args.interval, args.max_frames))
            if not args.video.is_file():
                raise FileNotFoundError(args.video)
            if args.index.exists():
                raise FileExistsError(f'Choose a new index path: {args.index} exists')
            print('Loading OpenCLIP (first run downloads weights)...', flush=True)
            started = perf_counter()
            encoder = OpenCLIPEncoder(args.model, args.pretrained, args.device,
                                      args.cache_dir, threads=args.threads)
            model_seconds = perf_counter() - started
            report = build_index(args.video, sampler, encoder, args.index, args.batch_size, args.dataset_manifest)
            report['model_load_seconds'] = model_seconds
            report['model_and_index_seconds'] = perf_counter() - started
            args.index.with_suffix('.metadata.json').write_text(json.dumps(report, indent=2) + '\n')
            print(f"Indexed {report['frames']} frames; payload {report['storage']['payload_bytes']:,} bytes; archive {report['index_file_bytes']:,} bytes")
            print(f'Saved {args.index} and {args.index.with_suffix(".metadata.json")}')
        else:
            if not args.query.strip():
                raise ValueError('Query cannot be empty')
            if args.output.exists():
                raise FileExistsError(f'Choose a new results directory: {args.output} exists')
            _, _, _, meta = load_index(args.index)
            config = meta['encoder']
            encoder = OpenCLIPEncoder(config['model'], config['pretrained'], args.device,
                                      args.cache_dir, seed=config['seed'], threads=args.threads)
            rows, meta = search_index(args.index, args.query, encoder, args.top_k)
            args.output.mkdir(parents=True)
            for row in rows:
                row['timestamp'] = format_time(row['seconds'])
                row['image'] = ''
            if not args.no_previews:
                export_previews(rows, meta, args.output, args.video)
            result = {'query': args.query, 'top_k': args.top_k, 'index': str(args.index.resolve()),
                      'index_sha256': sha256_file(args.index), 'encoder': encoder.metadata(),
                      'previews': not args.no_previews, 'results': rows}
            (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
            with (args.output / 'results.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            for row in rows:
                print(f"#{row['rank']} {row['timestamp']} cosine={row['cosine_similarity']:.6f}")
            print(f'Saved results to {args.output}; cosine scores are not probabilities.')
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
