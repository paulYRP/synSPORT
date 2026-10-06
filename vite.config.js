import { defineConfig } from 'vite';
import { execFileSync } from 'node:child_process';

let revision = process.env.GITHUB_SHA || 'local';
if (revision === 'local') {
  try { revision = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim(); } catch { /* Initial local build. */ }
}

export default defineConfig({
  base: '/synSPORT/',
  define: { __BUILD_REVISION__: JSON.stringify(revision) },
  build: { target: 'es2022' },
});
