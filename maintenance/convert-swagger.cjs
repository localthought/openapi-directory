// Invoke only the locked converter on prepared local data, never vendor code.
const fs = require('node:fs');
const converter = require('swagger2openapi');
const version = require('swagger2openapi/package.json').version;

async function main() {
  if (version !== '7.0.8') throw new Error('Installed swagger2openapi version differs from the recipe');
  const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  if (input.swagger !== '2.0') throw new Error('Conversion requires Swagger 2.0');
  const options = await converter.convertObj(input, {
    patch: true, warnOnly: true, resolve: false, targetVersion: '3.0.0',
    fetch: async () => { throw new Error('Network resolution is disabled during conversion'); }
  });
  const warnings = [];
  function walk(value, pointer = '#') {
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      const path = pointer + '/' + key.replace(/~/g, '~0').replace(/\//g, '~1');
      if (key === 'x-s2o-warning') warnings.push({pointer: path, message: child});
      walk(child, path);
    }
  }
  walk(options.openapi);
  fs.writeFileSync(process.argv[3], JSON.stringify({
    openapi: options.openapi, warnings, patches: options.patches
  }, null, 2) + '\n');
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
