"""Download a small real MP4 for smoke testing, recording source and checksum."""
import hashlib
import json
import urllib.request
from pathlib import Path

URL = 'https://download.samplelib.com/mp4/sample-5s.mp4'
EXPECTED_SHA256 = '05bd857af7f70bf51b6aac1144046973bf3325c9101a554bc27dc9607dbbd8f5'


def main():
    target = Path('data/sample.mp4')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    with urllib.request.urlopen(URL, timeout=60) as response:
        content = response.read()
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != EXPECTED_SHA256:
        raise ValueError('Sample content changed; verify its provenance before using it')
    target.write_bytes(content)
    info = {'url': URL, 'sha256': checksum, 'bytes': len(content),
            'purpose': 'Pipeline smoke test only; not a retrieval evaluation dataset'}
    target.with_suffix('.source.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
