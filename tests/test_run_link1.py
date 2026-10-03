import sys
import os
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src", "core"))
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

import gtraffic_runner

gtraffic_runner.run("https://direct.gtraffic.io/ufib3Q_", headless=True)
