import { execFileSync, spawnSync } from 'node:child_process';
import { copyFile, lstat, mkdir, mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export function validateApiConfig(config) {
  if (config.framework !== 'django' || config.routes || config.rewrites || config.redirects ||
      config.outputDirectory != null || config.buildCommand !== 'python manage.py collectstatic --noinput') {
    throw new Error('API deployment must use isolated Django configuration without website routes');
  }
}

export function includeApiFile(path) {
  const parts = path.split('/');
  const name = parts.at(-1);
  if (!path.startsWith('backend/') || parts.includes('..')) return false;
  if (parts.some(part => part.startsWith('.') && !['.python-version', '.vercelignore'].includes(part))) return false;
  if (parts.some(part => ['tests', '__pycache__', 'private-media', 'mediafiles', 'staticfiles'].includes(part))) return false;
  return name !== 'tests.py' && !name.startsWith('test_') && name !== 'pyproject.toml';
}

export async function packageApi(root = repository) {
  validateApiConfig(JSON.parse(await readFile(resolve(root, 'backend/vercel.json'), 'utf8')));
  const link = JSON.parse(await readFile(resolve(root, 'backend/.vercel/project.json'), 'utf8'));
  if (link.projectId !== 'prj_Xrcq616m9sKHvOV9Wts7RKkKOGv2') throw new Error('Unexpected API project');
  const target = await mkdtemp(resolve(tmpdir(), 'tynys-api-release-'));
  const files = execFileSync('git', ['ls-files', '-z', 'backend'], { cwd: root, encoding: 'utf8' }).split('\0').filter(includeApiFile);
  for (const path of files) {
    const source = resolve(root, path);
    if (!(await lstat(source)).isFile()) throw new Error(`Not a regular source file: ${path}`);
    const destination = resolve(target, path.slice('backend/'.length));
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(source, destination);
  }
  await mkdir(resolve(target, '.vercel'));
  await copyFile(resolve(root, 'backend/.vercel/project.json'), resolve(target, '.vercel/project.json'));
  return target;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = await packageApi();
  console.log(`Isolated Django artifact: ${target}`);
  if (process.argv.includes('--deploy')) {
    // Set the real process cwd BEFORE the CLI loads configuration. --cwd alone is unsafe.
    const cli = process.env.VERCEL_CLI;
    const command = cli ? process.execPath : 'vercel';
    const args = [...(cli ? [resolve(cli)] : []), '--local-config', resolve(target, 'vercel.json'),
      'deploy', '--prod', '--skip-domain', '--yes'];
    const result = spawnSync(command, args, { cwd: target, stdio: 'inherit' });
    if (result.error) throw result.error;
    process.exitCode = result.status ?? 1;
  }
}
