const fs = require('fs');
let code = fs.readFileSync('src/core/btd.js', 'utf-8');
const p1 = code.indexOf('function _0xfa19');
const p2 = code.indexOf('let nexusActiveToken');
global.document = { createElement: () => ({ setAttribute: () => {}, style: {} }), head: { appendChild: () => {} }, body: { appendChild: () => {} } };
const runner = code.substring(p1, p2) + '\nconst _0x32adda = _0xfa19;\nconsole.log("NEXUS_API_GATEWAY:", _0x32adda(2461) + _0x32adda(2465) + _0x32adda(1479) + _0x32adda(1937));';
eval(runner);
