"""Dataset crop/clip preparation CLI. See docs/DATA_PREPARATION.md."""
import argparse
import json
import shlex
from pathlib import Path

from video_search.preprocessing import (diagnose, export_cameras, init_config, load_config,
                           preview, select_cameras, window)


def main():
    parser = argparse.ArgumentParser(description='Reproducible FFmpeg traffic-grid preprocessing')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Probe source and create editable camera configuration')
    init.add_argument('--source', required=True, type=Path)
    init.add_argument('--config', required=True, type=Path)
    init.add_argument('--feeds', type=int, default=7)
    init.add_argument('--hash-source', action='store_true', help='Also compute a full checksum (reads the entire file once)')
    for name in ('preview', 'export', 'diagnose'):
        command = commands.add_parser(name)
        command.add_argument('--config', required=True, type=Path)
        command.add_argument('--output', required=True, type=Path)
        command.add_argument('--verify-full-hash', action='store_true', help='Read entire source and verify the optional full checksum')
        if name == 'preview':
            command.add_argument('--at', default='0')
            continue
        command.add_argument('--camera', action='append', help='Camera ID; repeat to select multiple (default: all defined crops)')
        command.add_argument('--start', default='0')
        limit = command.add_mutually_exclusive_group()
        limit.add_argument('--duration')
        limit.add_argument('--end')
        command.add_argument('--profile', choices=['smoke', 'dev', 'full'], default='smoke',
                             help='Default duration: smoke 30s, dev 300s, full to video end; duration/end overrides this')
        if name == 'export':
            command.add_argument('--dry-run', action='store_true')
        else:
            command.add_argument('--mad-threshold', type=float, default=2.)
            command.add_argument('--pixel-delta', type=float, default=8.)
            command.add_argument('--min-fraction', type=float, default=.01)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            config = init_config(args.source, args.config, args.feeds, args.hash_source)
            print(f'Saved {args.config}. Define crops using [x,y,width,height]; null crops are excluded.')
            meta = config['source']['metadata']
            print(f'{meta["width"]}x{meta["height"]}; average FPS {meta["avg_frame_rate"]}; video duration {meta["video_duration_seconds"]:.6f} s')
            return
        config = load_config(args.config, args.verify_full_hash)
        if args.command == 'preview':
            preview(config, args.at, args.output)
            print(f'Saved unscaled source, coordinate overlay and crop PNGs to {args.output}')
            return
        cameras = select_cameras(config, args.camera)
        start, end = window(config, args.start, args.duration, args.end, args.profile)
        if args.command == 'export':
            result = export_cameras(config, cameras, start, end, args.output, args.dry_run)
            if args.dry_run:
                for command in result['commands']:
                    print(shlex.join(command))
            else:
                print(f'Saved {len(cameras)} camera MP4s with verified per-frame timeline mappings in {args.output}')
        else:
            if args.output.exists():
                raise FileExistsError(f'Use a new diagnostic directory: {args.output}')
            for camera in cameras:
                report = diagnose(config, camera, start, end, args.output / camera['id'],
                                  args.mad_threshold, args.pixel_delta, args.min_fraction)
                print(f'{camera["id"]}: recording {report["observed_recording_fps"]:.3f} FPS; '
                      f'observable changes {report["observable_update_hz"]:.3f} Hz; '
                      f'{report["observable_updates"]} events; not true sensor/network FPS')
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'Error: {error}\n')


if __name__ == '__main__':
    main()
