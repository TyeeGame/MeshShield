from pathlib import Path
import argparse
p = argparse.ArgumentParser()
p.add_argument('--node', type=int, choices=(1, 2), required=True)
a = p.parse_args()
path = Path(__file__).resolve().parents[1] / 'firmware/xenon/src/node_config.h'
path.write_text(f'#pragma once\n#define MESH_NODE {a.node}\n')
print(f'{path}: node {a.node}, address 0x{0x20+a.node:02x}')
