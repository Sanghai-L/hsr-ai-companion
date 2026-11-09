// Run using the installed Electron in Node mode; reads static package files only.
const fs = require('node:fs');
const path = require('node:path');
const base = 'E:/Deepseek Harness/resources/app.asar/dsh/node_modules/@deepseek-ai';
const dest = path.resolve(__dirname, '../../.local/evidence/D005/dsh-install');
fs.mkdirSync(dest, {recursive: true});
const names = fs.readdirSync(base).filter(n => /mcp|headless|profile|web|cordis|app-boot|instruct|rules/.test(n));
fs.writeFileSync(path.join(dest,'package-names.json'),JSON.stringify(names,null,2));
for (const name of names) {
  const pkg = path.join(base, name, 'package.json');
  if (fs.existsSync(pkg)) fs.writeFileSync(path.join(dest,name+'.package.json'),fs.readFileSync(pkg));
  if (name === 'dsh-mcp-client') {
    for (const file of ['lib/probe.js','lib/index.js','lib/types.js','README.md']) {
      const target = path.join(base,name,file);
      if (fs.existsSync(target)) fs.writeFileSync(path.join(dest,'mcp-'+path.basename(file)),fs.readFileSync(target));
    }
  }
}
for (const [name,file] of [
  ['cordis-plugin-loader','lib/index.js'],
  ['dsh-app-boot','lib/index.js'],
  ['dsh-agent-instructions','lib/index.js'],
  ['dsh-headless','lib/index.js'],
  ['dsh-cordis-host-runner','lib/index.js']
]) {
  const target=path.join(base,name,file);
  if(fs.existsSync(target)) fs.writeFileSync(path.join(dest,name+'.index.js'),fs.readFileSync(target));
}
fs.writeFileSync(path.join(dest,'dsh-package-names.json'),JSON.stringify(fs.readdirSync(base),null,2));
for (const name of ['dsh-base','dsh-headless']) {
  for(const file of ['cordis.patch.yml','package.json','README.md']) {
    const target=path.join(base,name,file);
    if(fs.existsSync(target)) fs.writeFileSync(path.join(dest,name+'.'+file),fs.readFileSync(target));
  }
}
process.stdout.write(JSON.stringify({staticPackages:names}));
