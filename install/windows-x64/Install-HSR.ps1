param(
  [Parameter(Mandatory=$true)][string]$Workspace,
  [ValidateSet('install','rollback','uninstall','recover')][string]$Action = 'install',
  [string]$ProgramRoot,
  [string]$DataDir,
  [switch]$Offline,
  [switch]$PurgeData
)
$ErrorActionPreference = 'Stop'
function Get-HsrFileHash([string]$LiteralPath) {
  $hsrStream = [IO.File]::OpenRead($LiteralPath)
  $hsrHasher = [Security.Cryptography.SHA256]::Create()
  try { return [BitConverter]::ToString($hsrHasher.ComputeHash($hsrStream)).Replace('-', '').ToLowerInvariant() }
  finally { $hsrStream.Dispose(); $hsrHasher.Dispose() }
}
$hsrWorkspace = [IO.Path]::GetFullPath($Workspace)
if (-not $ProgramRoot) { $ProgramRoot = Join-Path $hsrWorkspace '.hsr-program' }
if (-not $DataDir) { $DataDir = Join-Path $hsrWorkspace '.local/player' }
$hsrArchive = Join-Path $PSScriptRoot 'bootstrap.zip'
if ((Get-HsrFileHash $hsrArchive) -ne 'e399ae6e6bba0bd149d2e50245a131237c02857b3502200ef58ad547d279b888') { throw '引导介质校验失败，未执行程序' }
if ((Get-HsrFileHash (Join-Path $PSScriptRoot 'trust.json')) -ne '1d6b7efa09b4e9acd1d90e1949bbde6d02d365a6f84c8ed699d318e973531b4a') { throw '固定的发布公钥文件发生变化' }
$hsrParent = Join-Path $hsrWorkspace '.hsr-bootstrap'
$hsrTemporary = Join-Path $hsrParent ([guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $hsrTemporary -Force | Out-Null
$hsrTemporary = (Resolve-Path -LiteralPath $hsrTemporary).Path
$hsrExit = 1
try {
  [Reflection.Assembly]::LoadWithPartialName('System.IO.Compression.FileSystem') | Out-Null
  [IO.Compression.ZipFile]::ExtractToDirectory($hsrArchive, $hsrTemporary)
  $hsrPython = Join-Path $hsrTemporary 'runtime/python.exe'
  $hsrOptions = @('--data-dir', [IO.Path]::GetFullPath($DataDir))
  if ($Offline) { $hsrOptions += '--offline' }
  $hsrOptions += ($Action + '-program')
  $hsrOptions += @('--root', [IO.Path]::GetFullPath($ProgramRoot), '--trust', (Join-Path $PSScriptRoot 'trust.json'))
  if ($Action -eq 'install') { $hsrOptions += @('--package', (Join-Path $PSScriptRoot 'hsr-companion-0.1.3-windows-x64.json')) }
  if ($PurgeData -and $Action -ne 'uninstall') { throw 'PurgeData只适用于单独选择清理资料的卸载' }
  if ($PurgeData) { $hsrOptions += '--purge-data' }
  & $hsrPython -I -m companion @hsrOptions
  $hsrExit = $LASTEXITCODE
  if ($hsrExit -eq 0 -and $Action -eq 'install') {
    $hsrConfigOptions = @('--data-dir', [IO.Path]::GetFullPath($DataDir))
    if ($Offline) { $hsrConfigOptions += '--offline' }
    $hsrConfigOptions += @('configure-codex', '--root', [IO.Path]::GetFullPath($ProgramRoot), '--workspace', $hsrWorkspace)
    & $hsrPython -I -m companion @hsrConfigOptions
    $hsrExit = $LASTEXITCODE
  }
} finally {
  $hsrVerifiedParent = [IO.Path]::GetFullPath($hsrParent).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
  $hsrVerifiedTarget = [IO.Path]::GetFullPath($hsrTemporary)
  if (-not $hsrVerifiedTarget.StartsWith($hsrVerifiedParent, [StringComparison]::OrdinalIgnoreCase)) { throw '临时清理路径越界' }
  if ((Split-Path -Leaf $hsrVerifiedTarget) -notmatch '^[0-9a-f]{32}$') { throw '临时目录名称不安全' }
  Remove-Item -LiteralPath $hsrVerifiedTarget -Recurse -Force
}
exit $hsrExit
