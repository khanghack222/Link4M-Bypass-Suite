const fs = require('fs');
let code = fs.readFileSync('src/core/btd.js', 'utf-8');
global.window = { location: { href: 'https://mu88.fund/', origin: 'https://mu88.fund' } };
global.document = {
    referrer: 'https://www.google.com/',
    createElement: () => ({ setAttribute: () => {}, style: {} }),
    head: { appendChild: () => {} },
    body: { appendChild: () => {} },
    cookie: ''
};
global.navigator = { userAgent: 'Mozilla/5.0' };
code += '\nconsole.log("NEXUS_API_GATEWAY:", NEXUS_API_GATEWAY);\nprocess.exit(0);';
eval(code);
