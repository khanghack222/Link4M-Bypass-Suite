const fs = require('fs');
let code = fs.readFileSync('src/core/btd.js', 'utf-8');
const p2 = code.indexOf('let nexusActiveToken');
global.document = { createElement: () => ({ setAttribute: () => {}, style: {} }), head: { appendChild: () => {} }, body: { appendChild: () => {} } };
const runner = code.substring(0, p2) + '\nconsole.log("NEXUS_API_GATEWAY:", NEXUS_API_GATEWAY);';
eval(runner);
