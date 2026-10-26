param(
  [string]$Model = "nemotron-3-nano:4b",
  [ValidateRange(1,5)][int]$Repeats = 3,
  [ValidateRange(60,420)][int]$TimeoutSeconds = 420,
  [string]$OutputDir = ""
)
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $dir "..\..")).Path
if (-not $OutputDir) {
  $OutputDir = Join-Path (Split-Path -Parent $repo) "local-nemotron-comparison"
}
$results = [IO.Path]::GetFullPath($OutputDir)
if ($results.StartsWith($repo + [IO.Path]::DirectorySeparatorChar,
      [StringComparison]::OrdinalIgnoreCase)) {
  throw "Resultados devem ficar fora do checkout."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker ausente." }
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop indisponivel." }
if (Test-Path (Join-Path $results "report.json")) { throw "Use uma pasta de saida nova." }
New-Item -ItemType Directory -Force -Path $results | Out-Null
$image = "local-nemotron4b-comparison:cloi-2.1.0"
docker build --file (Join-Path $dir "Dockerfile") --tag $image $dir
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar imagem isolada." }
$dockerArgs = @(
  "run","--rm","--network","host","--read-only",
  "--cap-drop","ALL","--security-opt","no-new-privileges",
  "--pids-limit","128","--memory","3g","--cpus","2",
  "--tmpfs","/tmp:rw,exec,nosuid,size=512m",
  "--mount","type=bind,source=$dir,target=/app/benchmarks/nemotron4b,readonly",
  "--mount","type=bind,source=$(Join-Path $repo 'experiments\local07'),target=/app/experiments/local07,readonly",
  "--mount","type=bind,source=$results,target=/results",
  $image,"--model",$Model,"--repeats",$Repeats,"--timeout",$TimeoutSeconds
)
& docker @dockerArgs
$exit = $LASTEXITCODE
Write-Host "Evidencia: $results"
if ($exit -eq 2) { throw "BLOCKED: host networking, Ollama ou modelo Q4_K_M." }
if ($exit -ne 0) { Write-Warning "Ao menos uma tentativa nao passou nos testes funcionais." }
exit $exit
