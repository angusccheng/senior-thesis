"""Analyze every recorded frame once; outputs evidence, not full camera videos."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from video_search.availability import analyze

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/nyc_traffic.json')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();analyze(args.config,args.output)
