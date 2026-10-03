const fs = require('fs');
let code = fs.readFileSync('src/core/btd.js', 'utf-8');
const p1 = code.indexOf('const NEXUS_API_GATEWAY =');
console.log(code.substring(p1, p1 + 150));
