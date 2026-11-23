// Select an unoccupied loopback candidate; backend_control.py performs the final check.
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

export async function portIsFree(port) {
  if (!Number.isInteger(port) || port < 1024 || port > 65535) return false;
  const server = createServer();
  return new Promise(done => {
    server.once('error', () => done(false));
    server.listen({ host: '127.0.0.1', port, exclusive: true },
      () => server.close(() => done(true)));
  });
}

export async function selectAvailablePort({ excluded = [8159, 8162], attempts = 24 } = {}) {
  const forbidden = new Set(excluded);
  for (let n = 0; n < attempts; n++) {
    const server = createServer();
    const candidate = await new Promise((done, reject) => {
      server.once('error', reject);
      server.listen({ host: '127.0.0.1', port: 0, exclusive: true }, () => {
        const value = server.address().port;
        server.close(error => error ? reject(error) : done(value));
      });
    });
    if (!forbidden.has(candidate) && await portIsFree(candidate)) return candidate;
  }
  throw new Error('No suitable loopback port; no process stopped');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  console.log(await selectAvailablePort());
