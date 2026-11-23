// Resolve only Playwright imports against existing Windows runtime modules.
// No symlinks, downloads, installs or writes to the personal runtime.
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const runtime = process.env.N3LX_RELEASE_TEST_RUNTIME;
if (!runtime) throw new Error('BLOCKED: Playwright runtime is not configured');
const fromRuntime = createRequire(join(runtime, 'package.json'));

export async function resolve(specifier, context, nextResolve) {
  if (specifier === '@playwright/test' ||
      specifier.startsWith('@playwright/test/') ||
      specifier === 'playwright' || specifier.startsWith('playwright/')) {
    let path = fromRuntime.resolve(specifier);
    if (path.endsWith('.js') && existsSync(path.slice(0, -3) + '.mjs'))
      path = path.slice(0, -3) + '.mjs';
    return nextResolve(pathToFileURL(path).href, context);
  }
  return nextResolve(specifier, context);
}
