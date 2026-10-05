import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.dirname(desktopRoot);
const androidRoot = path.join(desktopRoot, 'src-tauri', 'gen', 'android');
const stageRoot = path.join(desktopRoot, '.engine-build', 'android', 'source');
const engineRoot = path.join(desktopRoot, 'engine', 'android');

// Never point Python's source directory at the repository: it contains .env,
// signing material, databases and user PDFs which must not ship in an APK.
const allowedDirectories = ['app_core', 'app_security', 'models', 'routes/api_v1', 'schemas', 'services'];
const sourceFiles = new Set(['fastapi_app.py', 'routes/__init__.py', 'checkpoints/best_patterns.json']);
const candidates = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '--', ...allowedDirectories],
  { cwd: repoRoot, encoding: 'utf8' }).split(/\r?\n/).filter(Boolean);
for (const relative of candidates) {
  if (relative.endsWith('.py') && !relative.includes('__pycache__')) sourceFiles.add(relative);
}
console.log(`Collecting ${sourceFiles.size + 1} Android engine source files.`);

await fs.mkdir(stageRoot, { recursive: true });
const manifestPath = path.join(path.dirname(stageRoot), 'sources.json');
let previous = [];
try { previous = JSON.parse(await fs.readFile(manifestPath, 'utf8')).files.map(item => item.path); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
for (const relative of previous) {
  if (sourceFiles.has(relative) || relative === 'mobile_engine.py') continue;
  const target = path.resolve(stageRoot, relative);
  if (!target.startsWith(`${stageRoot}${path.sep}`)) throw new Error('Invalid staging manifest path');
  await fs.rm(target, { force: true });
}
const manifest = [];
for (const relative of [...sourceFiles].sort()) {
  if ((await fs.lstat(path.join(repoRoot, relative))).isSymbolicLink()) throw new Error('Symbolic links are not allowed in engine sources.');
  const data = await fs.readFile(path.join(repoRoot, relative));
  const target = path.join(stageRoot, relative);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, data);
  manifest.push({ path: relative, sha256: createHash('sha256').update(data).digest('hex') });
}
await fs.copyFile(path.join(engineRoot, 'mobile_engine.py'), path.join(stageRoot, 'mobile_engine.py'));
manifest.push({ path: 'mobile_engine.py', sha256: createHash('sha256').update(await fs.readFile(path.join(engineRoot, 'mobile_engine.py'))).digest('hex') });
await fs.writeFile(manifestPath, JSON.stringify({ files: manifest }, null, 2));

const publicEnvironment = Object.fromEntries((await fs.readFile(path.join(repoRoot, 'frontend', '.env.mobile'), 'utf8'))
  .split(/\r?\n/).filter(line => /^VITE_SUPABASE_(URL|PUBLISHABLE_KEY)=/.test(line))
  .map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1).trim()]; }));
if (!publicEnvironment.VITE_SUPABASE_URL?.startsWith('https://') ||
    !publicEnvironment.VITE_SUPABASE_PUBLISHABLE_KEY?.startsWith('sb_publishable_')) {
  throw new Error('The Android engine requires the public Supabase configuration.');
}
const bundledPython = path.join(os.homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe');
const buildPython = process.env.CONCURSE_ANDROID_BUILD_PYTHON || bundledPython;
const version = execFileSync(buildPython, ['-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'],
  { encoding: 'utf8', timeout: 30000 }).trim();
if (version !== '3.12') throw new Error('Set CONCURSE_ANDROID_BUILD_PYTHON to a Python 3.12 executable.');
const propertyValue = value => value.replaceAll('\\', '\\\\').replaceAll('\n', '\\n').replaceAll('\r', '\\r');
await fs.writeFile(path.join(androidRoot, 'concurse-engine.properties'), [
  `buildPython=${propertyValue(buildPython)}`,
  `supabaseUrl=${propertyValue(JSON.stringify(publicEnvironment.VITE_SUPABASE_URL))}`,
  `publishableKey=${propertyValue(JSON.stringify(publicEnvironment.VITE_SUPABASE_PUBLISHABLE_KEY))}`,
].join('\n') + '\n');

const topGradle = path.join(androidRoot, 'build.gradle.kts');
let top = await fs.readFile(topGradle, 'utf8');
if (!top.includes('com.chaquo.python:gradle')) {
  const anchor = 'classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.25")';
  if (!top.includes(anchor)) throw new Error('Review the generated Gradle configuration before preparing the engine.');
  top = top.replace(anchor, `${anchor}\n        classpath("com.chaquo.python:gradle:17.0.0")`);
  await fs.writeFile(topGradle, top);
}
const appGradle = path.join(androidRoot, 'app', 'build.gradle.kts');
let app = await fs.readFile(appGradle, 'utf8');
if (!app.includes('id("com.chaquo.python")')) app = app.replace('id("rust")', 'id("rust")\n    id("com.chaquo.python")');
const begin = '// BEGIN CONCURSE ANDROID ENGINE';
const end = '// END CONCURSE ANDROID ENGINE';
if (app.includes(begin)) app = app.slice(0, app.indexOf(begin)) + app.slice(app.indexOf(end) + end.length);
app = `${app.trimEnd()}\n\n${begin}\n${await fs.readFile(path.join(engineRoot, 'engine.gradle.kts'), 'utf8')}\n${end}\n`;
await fs.writeFile(appGradle, app);
await fs.copyFile(path.join(engineRoot, 'MainActivity.kt'), path.join(androidRoot, 'app', 'src', 'main', 'java', 'io', 'concurse', 'desktop', 'MainActivity.kt'));
await fs.copyFile(path.join(engineRoot, 'ProcessingService.kt'), path.join(androidRoot, 'app', 'src', 'main', 'java', 'io', 'concurse', 'desktop', 'ProcessingService.kt'));
const testDir = path.join(androidRoot, 'app', 'src', 'androidTest', 'java', 'io', 'concurse', 'desktop');
await fs.mkdir(testDir, { recursive: true });
await fs.rm(path.join(testDir, 'EngineSmokeTest.kt'), { force: true });
await fs.copyFile(path.join(engineRoot, 'EngineSmokeTest.java'), path.join(testDir, 'EngineSmokeTest.java'));
await fs.copyFile(path.join(engineRoot, 'engine.pro'), path.join(androidRoot, 'app', 'concurse-engine.pro'));
await fs.copyFile(path.join(engineRoot, 'network_security_config.xml'), path.join(androidRoot, 'app', 'src', 'main', 'res', 'xml', 'engine_network_security_config.xml'));
const manifestFile = path.join(androidRoot, 'app', 'src', 'main', 'AndroidManifest.xml');
let androidManifest = await fs.readFile(manifestFile, 'utf8');
if (!androidManifest.includes('android:networkSecurityConfig=')) {
  androidManifest = androidManifest.replace('<application', '<application\n        android:networkSecurityConfig="@xml/engine_network_security_config"');
}
if (!androidManifest.includes('android.permission.FOREGROUND_SERVICE"')) {
  androidManifest = androidManifest.replace('<application', '<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />\n\n    <application');
}
if (!androidManifest.includes('android:name=".ProcessingService"')) {
  androidManifest = androidManifest.replace('</application>', '<service android:name=".ProcessingService" android:exported="false" android:foregroundServiceType="dataSync" />\n    </application>');
}
await fs.writeFile(manifestFile, androidManifest);
console.log(`Android processing engine prepared with ${manifest.length} source files.`);
