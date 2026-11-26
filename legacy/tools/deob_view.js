const fs = require('fs');

const code = fs.readFileSync('tmp_view.js', 'utf8');

// Parse _0x3797 array
const arrMatch = code.match(/function\s+_0x3797\s*\(\)\s*\{[\s\S]*?return\s+_0x[a-f0-9]+;\s*\}/);
const rotMatch = code.match(/\(function\s*\(_0x[a-f0-9]+,\s*_0x[a-f0-9]+\)\s*\{[\s\S]*?\}\(_0x3797,\s*0x[a-f0-9]+\)\);/);
const lookMatch = code.match(/function\s+_0x2164\s*\([^)]*\)\s*\{[\s\S]*?return\s+_0x[a-f0-9]+;\s*\}/);

if (!arrMatch || !rotMatch || !lookMatch) {
    console.error('Cannot match regex');
    process.exit(1);
}

const deobContext = `
${arrMatch[0]}
${rotMatch[0]}
${lookMatch[0]}
global._0x2164 = _0x2164;
`;

eval(deobContext);

let deobCode = code.replace(/_0x(?:eb8628|257eae|131b1c|5a8907|4f163a|34457f|5d14f4|4d6def|2164)\((0x[a-f0-9]+)\)/g, (m, hex) => {
    try {
        const val = global._0x2164(parseInt(hex, 16));
        return JSON.stringify(val);
    } catch(e) {
        return m;
    }
});

fs.writeFileSync('deobf_view_clean.js', deobCode, 'utf8');
console.log('Successfully saved deobf_view_clean.js');
