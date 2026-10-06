import { readdir, readFile, lstat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'dist');
const base = '/synSPORT/';
const failures = [];

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    const relative = path.relative(output, absolute).split(path.sep).join('/');
    // lstat distinguishes a real link from a OneDrive file reparse point on Windows.
    const metadata = await lstat(absolute);
    if (metadata.isSymbolicLink()) failures.push(`Unexpected symbolic link: ${relative}`);
    else if (metadata.isDirectory()) files.push(...await walk(absolute));
    else files.push(relative);
  }
  return files;
}

const files = await walk(output);
const names = new Set(files);
for (const required of ['index.html', 'chapters/framework.html', 'chapters/objective.html', 'media/judoka.png', 'media/throw.mp4', 'media/motion.json', 'media/CREDITS.md', 'fonts/roboto.css', 'fonts/OFL.txt']) {
  if (!names.has(required)) failures.push(`Missing runtime file: ${required}`);
}
for (const file of files) {
  if (/(^|\/)(dev|node_modules|\.git|\.github|\.reference-browser|\.review-browser)(\/|$)/i.test(file)
      || /\.(xlsx?|csv|rds|rdata|rmd|blend|pt|pth|zip|py)$/i.test(file)) {
    failures.push(`Development or source-data artifact in deployment: ${file}`);
  }
  const stats = await lstat(path.join(output, file));
  if (stats.size === 0) failures.push(`Empty deployment file: ${file}`);
}

const html = await readFile(path.join(output, 'index.html'), 'utf8');
if (!/<title>[^<]+<\/title>/i.test(html)) failures.push('The entry page has no title.');
if (!html.includes(base)) failures.push(`The entry page does not use the project base ${base}.`);
if (/C:[\\/]+Users[\\/]|file:\/\/|\.\.\/dev\//i.test(html)) failures.push('The entry page includes a local-only path.');
for (const file of files.filter(name => /\.(html|css)$/i.test(name))) {
  const contents = await readFile(path.join(output, file), 'utf8');
  const links = file.endsWith('.html')
    ? [...contents.matchAll(/(?:src|href)\s*=\s*["']([^"']+)["']/gi)].map(match => match[1])
    : [...contents.matchAll(/url\(\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^)]*))\s*\)/gi)].map(match => (match[1] ?? match[2] ?? match[3]).trim());
  for (const link of links) {
    if (/^(https?:|data:|mailto:|tel:|#)/i.test(link)) continue;
    const resolved = new URL(link, `https://build.invalid${base}${file}`);
    const pathname = decodeURIComponent(resolved.pathname);
    if (!pathname.startsWith(base)) {
      failures.push(`Resource escapes the project base in ${file}: ${link}`);
      continue;
    }
    const relative = pathname.slice(base.length);
    if (relative && !names.has(relative)) failures.push(`Missing resource in ${file}: ${link}`);
  }
}

if (failures.length) {
  console.error(failures.map(message => `- ${message}`).join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Verified ${files.length} deployment files, runtime credits, project-base links and source-data exclusion.`);
}
