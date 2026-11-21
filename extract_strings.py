import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

# Let's extract _0x3797 array and the shifter function
with open('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/view.js', 'r', encoding='utf-8') as f:
    code = f.read()

# Let's run a js snippet with python's js engine or emulate _0x2164 in Python!
# Let's extract the array definition
arr_match = re.search(r'var _0x39d2c4=\[(.*?)\];function _0x3797', code, re.DOTALL)
if not arr_match:
    arr_match = re.search(r'var _0x39d2c4=(\[.*?\]);_0x3797', code, re.DOTALL)

# Let's find function _0x2164
func_match = re.search(r'function _0x2164\((.*?)\)\{.*?\n\}', code)
print("Func match:", func_match.group(0) if func_match else "None")
