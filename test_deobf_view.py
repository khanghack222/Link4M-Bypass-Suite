with open('scratch_link4m_view.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Let's inspect the first 100 lines of view.js
lines = js.splitlines()
print(f"Total lines: {len(lines)}")
for i in range(min(50, len(lines))):
    print(f"{i+1}: {lines[i][:120]}")
