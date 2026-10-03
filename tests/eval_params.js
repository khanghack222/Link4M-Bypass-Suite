const fs = require('fs');
let code = fs.readFileSync('src/core/btd.js', 'utf-8');
const p1 = code.indexOf('function _0xfa19');
const p2 = code.indexOf('function injectNexusStyles');
const runner = code.substring(p1, p2) + '\nconsole.log(_0xfa19(2461), _0xfa19(2465), _0xfa19(1479), _0xfa19(1937));';
eval(runner);
