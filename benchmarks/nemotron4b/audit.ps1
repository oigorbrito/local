param(
    [string[]]$EvidenceRoots = @(
        "D:\projetos\local-nemotron-comparison",
        "D:\projetos\local-nemotron-comparison-20261025-234149"
    ),
    [string]$OutputDir = ""
)
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $dir "..\..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path (Split-Path -Parent $repo) (
        "local-nemotron-audit-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
    )
}
if (Test-Path -LiteralPath $OutputDir) {
    throw "Use um diretorio de auditoria novo."
}
foreach ($root in $EvidenceRoots) {
    if (-not (Test-Path -LiteralPath (Join-Path $root 'report.json') -PathType Leaf)) {
        throw "Evidencia indisponivel: $root"
    }
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker ausente." }
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Engine indisponivel." }
$image = "local-nemotron4b-comparison:cloi-2.1.0"
docker image inspect $image | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Imagem do benchmark ausente. Execute a etapa de build do run.ps1."
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null

$argsDocker = @(
    'run', '--rm', '--network', 'none', '--read-only',
    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
    '--pids-limit', '128', '--memory', '3g', '--cpus', '2',
    '--tmpfs', '/tmp:rw,exec,nosuid,size=512m',
    '--mount', ('type=bind,source=' + $dir + ',target=/app/benchmarks/nemotron4b,readonly'),
    '--mount', ('type=bind,source=' + (Join-Path $repo 'experiments\local07') +
                ',target=/app/experiments/local07,readonly'),
    '--mount', ('type=bind,source=' + $OutputDir + ',target=/audit-out'),
    '--entrypoint', 'python3'
)
$argsAudit = @(
    '/app/benchmarks/nemotron4b/offline_audit.py',
    '--fixture', '/app/benchmarks/nemotron4b/fixture',
    '--adapter', '/app/experiments/local07',
    '--output', '/audit-out'
)
for ($i = 0; $i -lt $EvidenceRoots.Count; $i++) {
    $target = "/evidence-$i"
    $argsDocker += @(
        '--mount', ('type=bind,source=' + $EvidenceRoots[$i] + ',target=' + $target + ',readonly')
    )
    $argsAudit += @('--evidence', $target)
}
# Docker CLI flags must precede the image name.
& docker @argsDocker $image @argsAudit
$exit = $LASTEXITCODE

Write-Host "Auditoria offline: $OutputDir"
$report = Join-Path $OutputDir 'offline-audit.json'
if (Test-Path -LiteralPath $report) {
    Get-Content -LiteralPath $report -Raw
    Get-FileHash -LiteralPath $report -Algorithm SHA256
}
if ($exit -ne 0) {
    throw "Auditoria incompleta; preservar logs no diretorio indicado."
}
