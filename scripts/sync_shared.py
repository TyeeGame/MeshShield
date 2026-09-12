"""Package canonical headers inside each self-contained Particle project."""
from pathlib import Path
import argparse
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--check', action='store_true')
a = p.parse_args()
for project in ('argon',):
    for source in (ROOT / 'shared').glob('*.h'):
        dest = ROOT / 'firmware' / project / 'src' / source.name
        if a.check:
            assert dest.read_bytes() == source.read_bytes(), f'Run scripts/sync_shared.py: {dest}'
        else:
            dest.write_bytes(source.read_bytes())
