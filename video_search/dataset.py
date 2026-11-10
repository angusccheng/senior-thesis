"""Shared footage eligibility and timestamp provenance, independent of representation."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def checked_intervals(values):
    previous=-float('inf')
    for start,end in values:
        if not np.isfinite([start,end]).all() or start<0 or end<=start or start<previous:
            raise ValueError('Dataset eligibility intervals must be sorted, nonoverlapping, finite and positive')
        previous=end
    return values


class DatasetContext:
    def __init__(self, path, video, video_sha256):
        path=Path(path).resolve();self.metadata=json.loads(path.read_text())
        if self.metadata['schema_version']!=1:raise ValueError('Unsupported dataset manifest schema')
        if self.metadata['video']['sha256']!=video_sha256:
            raise ValueError('Dataset manifest does not identify this cropped video')
        self.metadata['manifest_path']=str(path)
        self.metadata['manifest_sha256']=file_hash(path)
        mapping=self.metadata['timestamp_mapping']
        mapping_path=Path(mapping['path'])
        if not mapping_path.is_absolute():mapping_path=path.parent/mapping_path
        if file_hash(mapping_path)!=mapping['sha256']:raise ValueError('Dataset timestamp mapping checksum mismatch')
        self.rows={}
        previous=None
        with mapping_path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                number=int(row['frame'])
                if number in self.rows:raise ValueError('Duplicate dataset frame mapping')
                pair=(float(row['cropped_seconds']),float(row['source_seconds']))
                if number != len(self.rows) or not np.isfinite(pair).all() or min(pair)<0:
                    raise ValueError('Invalid dataset frame number or timestamp')
                if previous is not None and (pair[0]<=previous[0] or pair[1]<=previous[1]):
                    raise ValueError('Dataset timestamps must increase in both timelines')
                self.rows[number]=pair
                previous=pair
        self.valid=checked_intervals(self.metadata['valid_source_intervals'])
        if self.metadata['availability_policy']!='exclude_confirmed_unavailable_only':
            raise ValueError('Unsupported dataset eligibility policy')
        if 'availability_report' in self.metadata:
            report=self.metadata['availability_report'];report_path=Path(report['path'])
            if not report_path.is_absolute():report_path=path.parent/report_path
            if file_hash(report_path)!=report['sha256']:raise ValueError('Availability report checksum mismatch')

    def source_time(self, frame):
        if frame.number not in self.rows:raise ValueError('Frame missing from dataset timestamp mapping')
        cropped,source=self.rows[frame.number]
        if abs(cropped-frame.seconds)>2e-6:raise ValueError('Dataset and cropped-video timestamps disagree')
        return source

    def eligible(self, frame):
        source=self.source_time(frame)
        return any(start-1e-9<=source<end-1e-9 for start,end in self.valid)

    def timestamps(self, frames):
        return np.array([self.source_time(frame) for frame in frames],dtype=np.float64)
