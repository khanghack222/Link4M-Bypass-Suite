import re

exe_path = r"C:\Users\XUAN\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe"
with open(exe_path, "rb") as f:
    data = f.read()

# search for PromptInput =
for m in re.finditer(rb'PromptInput\s*=\s*r\.Struct\(\{([^}]+)\}\)', data):
    print("PromptInput fields:", m.group(1).decode("ascii", errors="ignore"))

# or search for fields of PromptInput
for m in re.finditer(rb'PromptInput\s*=\s*[^;]+', data):
    print("PromptInput def:", m.group(0)[:200].decode("ascii", errors="ignore"))
