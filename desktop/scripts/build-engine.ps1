$ErrorActionPreference = 'Stop'

$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $desktopRoot '..')).Path
$workspaceRoot = (Resolve-Path (Join-Path $repoRoot '..\..')).Path
$pythonCandidates = @(
  (Join-Path $repoRoot 'venv\Scripts\python.exe'),
  (Join-Path $workspaceRoot 'venv\Scripts\python.exe')
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = 'python' }

$null = & $python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
  & $python -m pip install -r (Join-Path $desktopRoot 'engine\requirements-build.txt')
}

$buildRoot = Join-Path $desktopRoot '.engine-build'
$distRoot = Join-Path $buildRoot 'dist'
$workRoot = Join-Path $buildRoot 'work'
$specRoot = Join-Path $buildRoot 'spec'
$targetRoot = Join-Path $desktopRoot 'src-tauri\binaries'
New-Item -ItemType Directory -Force -Path $distRoot, $workRoot, $specRoot, $targetRoot | Out-Null

$args = @(
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noconsole',
  '--name', 'concurse-engine',
  '--distpath', $distRoot, '--workpath', $workRoot, '--specpath', $specRoot,
  '--paths', $repoRoot,
  '--collect-all', 'rapidocr_onnxruntime',
  '--collect-binaries', 'onnxruntime',
  '--collect-data', 'onnxruntime',
  '--hidden-import', 'fastapi_app',
  (Join-Path $desktopRoot 'engine\server.py')
)
$rustBinary = @(
  (Join-Path $repoRoot 'concurse_core.pyd'),
  (Join-Path $workspaceRoot 'concurse_core.pyd')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (Test-Path $rustBinary) {
  $args = @('-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noconsole', '--name', 'concurse-engine', '--distpath', $distRoot, '--workpath', $workRoot, '--specpath', $specRoot, '--paths', $repoRoot, '--collect-all', 'rapidocr_onnxruntime', '--collect-binaries', 'onnxruntime', '--collect-data', 'onnxruntime', '--hidden-import', 'fastapi_app', '--add-binary', "$rustBinary;.", (Join-Path $desktopRoot 'engine\server.py'))
}
& $python @args
if ($LASTEXITCODE -ne 0) { throw 'A compilação do motor local falhou.' }

$target = Join-Path $targetRoot 'concurse-engine-x86_64-pc-windows-msvc.exe'
Copy-Item (Join-Path $distRoot 'concurse-engine.exe') $target -Force
Write-Output "Motor local criado em $target"
