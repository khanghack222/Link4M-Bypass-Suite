const fs = require('fs');

let code = fs.readFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/client_response.js', 'utf8');

// Find the string array function name and the rotation IIFE
// The string array function is function _0x6191() { ... }
// The rotation IIFE is (function(_0x2695e3, _0x3f4fb6) { ... })(_0x6191, 0x...);
// Let's extract them and evaluate them in a VM context so we can resolve any _0x... call!
const vm = require('vm');
const context = {};
vm.createContext(context);

// Let's find the lookup function definition
// It was: function _0x224f76(...) { return _0x19e3(...) }
// Let's inspect the first 2500 characters
console.log('Start of code:');
console.log(code.slice(0, 800));
