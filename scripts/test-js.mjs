// Run every JS test on Windows and POSIX, preserving failures from any file.
import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const files = readdirSync(new URL('../tests/js/', import.meta.url))
  .filter(name => name.endsWith('.test.mjs')).sort();
let failed = 0;
for (const file of files) {
  const result = spawnSync(process.execPath, [`tests/js/${file}`], { cwd: root, stdio: 'inherit' });
  if (result.error) console.error(result.error.message);
  if (result.error || result.status !== 0) failed++;
}
console.log(`JS files: ${files.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
