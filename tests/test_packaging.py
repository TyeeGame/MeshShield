import subprocess
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class PackagingTests(unittest.TestCase):
    def test_particle_projects_contain_identical_shared_headers(self):
        subprocess.run([sys.executable,str(ROOT/'scripts/sync_shared.py'),'--check'],check=True)

if __name__=='__main__':unittest.main()
