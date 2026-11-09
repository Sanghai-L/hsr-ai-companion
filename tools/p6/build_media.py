"""Build local install media. The initial script/public key need an independently trusted route."""
import argparse
import hashlib
import json
from pathlib import Path

from companion.contracts import canonical
from companion.release.artifacts import open_artifact, zip_files
from companion.release.signing import load_trust


def build(artifact, trust_path, output):
    artifact = artifact.resolve()
    content = artifact.read_bytes()
    keys = load_trust(trust_path)
    metadata, files, _ = open_artifact(content, keys)
    from companion.updates.source import ReleaseSource
    index = ReleaseSource(artifact.parent, trusted_keys=keys, require_signature=True).manifest("program")
    if index["artifact"] != artifact.name or index["sha256"] != hashlib.sha256(content).hexdigest():
        raise ValueError("候选包与签名发布索引不匹配")
    output.mkdir(parents=True, exist_ok=True)
    bootstrap = zip_files(files)
    fingerprint = hashlib.sha256(bootstrap).hexdigest()
    (output/"bootstrap.zip").write_bytes(bootstrap)
    (output/artifact.name).write_bytes(content)
    (output/"release.json").write_bytes((artifact.parent/"release.json").read_bytes())
    (output/"trust.json").write_bytes(canonical({"schema_version": 1, "keys": keys}))
    script = r'''param(
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
if ((Get-HsrFileHash $hsrArchive) -ne 'BOOTSTRAP_SHA256') { throw '引导介质校验失败，未执行程序' }
if ((Get-HsrFileHash (Join-Path $PSScriptRoot 'trust.json')) -ne 'TRUST_SHA256') { throw '固定的发布公钥文件发生变化' }
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
  if ($Action -eq 'install') { $hsrOptions += @('--package', (Join-Path $PSScriptRoot 'PROGRAM_FILENAME')) }
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
'''.replace("BOOTSTRAP_SHA256", fingerprint).replace("TRUST_SHA256", hashlib.sha256((output/"trust.json").read_bytes()).hexdigest()).replace("PROGRAM_FILENAME", artifact.name)
    (output/"Install-HSR.ps1").write_bytes(b"\xef\xbb\xbf"+script.encode("utf-8"))
    result = {"version": metadata["version"], "channel": metadata["channel"], "program_sha256": hashlib.sha256(content).hexdigest(),
              "bootstrap_sha256": fingerprint, "installer_sha256": hashlib.sha256((output/"Install-HSR.ps1").read_bytes()).hexdigest(),
              "program_artifact": artifact.name, "files": ["Install-HSR.ps1", "bootstrap.zip", artifact.name, "release.json", "trust.json"], "published": False}
    (output/"checksums.json").write_bytes(canonical(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--trust", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.artifact, args.trust, args.output), ensure_ascii=False))
