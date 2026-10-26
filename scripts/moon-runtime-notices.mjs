import { accessSync, constants, existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { basename, delimiter, dirname, resolve } from 'node:path';

function fail(message) {
  throw new Error(`Cannot identify MoonBit runtime notices: ${message}. Set MOON_HOME to the toolchain actually used for this build.`);
}

function samePath(a, b, platform) {
  return platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b;
}

function requireExecutable(file, platform) {
  try {
    if (!statSync(file).isFile()) fail(`not a regular executable: ${file}`);
    if (platform !== 'win32') accessSync(file, constants.X_OK);
  } catch (error) {
    fail(`unavailable executable ${file} (${error.message})`);
  }
  return file;
}

function inheritedPath(env, platform) {
  if (platform !== 'win32') {
    if (typeof env.PATH !== 'string' || !env.PATH) fail('PATH is absent or empty');
    return env.PATH;
  }
  const values = Object.entries(env).filter(([key]) => key.toLowerCase() === 'path').map(([, value]) => value);
  if (!values.length || values.some(value => typeof value !== 'string' || !value) || new Set(values).size !== 1) fail('PATH is absent, empty, or ambiguous');
  return values[0];
}

function firstPathExecutable(name, paths, cwd, platform) {
  for (let entry of paths.split(delimiter)) {
    if (platform === 'win32') {
      if (entry.startsWith('"') && entry.endsWith('"')) entry = entry.slice(1, -1);
      if (entry.includes('"')) fail('quoted PATH entry cannot be resolved reliably');
    }
    const directory = resolve(cwd, entry || '.');
    if (platform === 'win32') {
      for (const suffix of ['', '.com', '.cmd', '.bat']) {
        if (existsSync(resolve(directory, name + suffix))) fail(`unsupported PATH launcher may shadow ${name}.exe in ${directory}`);
      }
    }
    const file = resolve(directory, name + (platform === 'win32' ? '.exe' : ''));
    if (!existsSync(file)) continue;
    return requireExecutable(file, platform);
  }
  fail(`${name} was not found in PATH`);
}

function readRequiredText(file) {
  let bytes;
  try {
    if (!statSync(file).isFile()) fail(`not a regular attribution file: ${file}`);
    bytes = readFileSync(file);
  } catch (error) {
    fail(`unavailable attribution file ${file} (${error.message})`);
  }
  let text;
  try {
    // Preserve a source BOM and all body bytes when the build writes UTF-8 again.
    text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    fail(`attribution file is not valid UTF-8: ${file}`);
  }
  if (!text.trim()) fail(`empty attribution file: ${file}`);
  return text;
}

/** Resolve notices from the same logical MoonBit home used by runMoon.
 * Explicit/local homes override PATH. Only PATH fallback must prove that the
 * first moon and moonc come from the same bin; logical bin/lib junctions remain
 * valid and are never replaced with the real binary's parent directory.
 * This function reads files only. The caller may bind its own process MOON_HOME.
 */
export function resolveMoonRuntimeNotices({ root, env = process.env, cwd = process.cwd(), platform = process.platform }) {
  const localPath = resolve(root, '.local-toolchain.json');
  // runMoon reads local configuration even when an explicit home takes priority.
  const local = existsSync(localPath) ? JSON.parse(readFileSync(localPath, 'utf8')).moonHome : null;
  const configured = env.MOON_HOME || local;
  const source = env.MOON_HOME ? 'MOON_HOME' : local ? 'local-toolchain' : 'PATH';
  const suffix = platform === 'win32' ? '.exe' : '';
  let home;
  let selectedMoon;
  let selectedMoonc;
  if (configured) {
    if (typeof configured !== 'string') fail('configured moonHome is not a string');
    home = resolve(cwd, configured);
  } else {
    // Windows can search the child cwd before PATH. Refuse such a shadow rather
    // than silently selecting different binaries when the build pins a home.
    if (platform === 'win32') {
      for (const name of ['moon', 'moonc']) for (const ext of ['', '.exe', '.com', '.cmd', '.bat']) {
        if (existsSync(resolve(root, name + ext))) fail(`working-directory launcher can shadow PATH: ${name + ext}`);
      }
    }
    const paths = inheritedPath(env, platform);
    // runMoon starts its child in root, so relative/empty PATH entries use root.
    selectedMoon = firstPathExecutable('moon', paths, root, platform);
    selectedMoonc = firstPathExecutable('moonc', paths, root, platform);
    const bin = dirname(selectedMoon);
    if (!samePath(bin, dirname(selectedMoonc), platform) || !samePath(basename(bin), 'bin', platform)) fail('first PATH moon and moonc do not identify one logical home/bin');
    home = dirname(bin);
  }
  const moon = requireExecutable(resolve(home, 'bin', 'moon' + suffix), platform);
  const moonc = requireExecutable(resolve(home, 'bin', 'moonc' + suffix), platform);
  if (source === 'PATH' && (!samePath(realpathSync(moon), realpathSync(selectedMoon), platform) || !samePath(realpathSync(moonc), realpathSync(selectedMoonc), platform))) fail('PATH binaries do not match the resolved home');
  const licensePath = resolve(home, 'lib/core/LICENSE');
  const noticePath = resolve(home, 'lib/core/NOTICE');
  const licenseText = readRequiredText(licensePath);
  const noticeText = readRequiredText(noticePath);
  return Object.freeze({ home, source, moon, moonc, licensePath, noticePath, licenseText, noticeText });
}