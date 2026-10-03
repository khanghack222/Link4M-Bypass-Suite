const fs = require('fs');

let code = fs.readFileSync('scratch_link4m_view.js', 'utf8');

// Extract the array function and the lookup function
// The file starts with: var _0x4d6def=_0x2164;function _0x3797(){...} ...
// We can evaluate the array definition and lookup function in a clean context:
const context = {};
const match = code.match(/^(var\s+(_0x[a-f0-9]+)\s*=\s*(_0x[a-f0-9]+);function\s+(_0x[a-f0-9]+)\(\)\{[\s\S]*?\}\)\(\);\s*function\s+\3\([^)]+\)\{[\s\S]*?return\s+[^;]+;\s*\})/);

if (match) {
    console.log("Matched deobfuscation header!");
    const header = match[1];
    eval(header); // creates lookup function in global scope
    const lookupFnName = match[3];
    const lookupFn = eval(lookupFnName);
    const aliasName = match[2];

    // Now replace all occurrences of _0x4d6def(0x...) or lookupFn(0x...)
    const regex = new RegExp(`(?:${aliasName}|${lookupFnName})\\((0x[a-f0-9]+)\\)`, 'g');
    let deobf = code.replace(regex, (m, hex) => {
        try {
            const val = lookupFn(parseInt(hex, 16));
            return JSON.stringify(val);
        } catch (e) {
            return m;
        }
    });

    fs.writeFileSync('scratch_link4m_view_deobf.js', deobf, 'utf8');
    console.log("Saved scratch_link4m_view_deobf.js!");
} else {
    console.log("Could not match header regex!");
}
