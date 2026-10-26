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
$adapter = Join-Path $repo 'experiments\local07'
$relay = Join-Path $dir 'relay_host.py'
& python $relay --docker-image $image --benchmark-dir $dir --adapter-dir $adapter --results-dir $results --model $Model --repeats $Repeats --timeout $TimeoutSeconds
$exit = $LASTEXITCODE
Write-Host "Evidencia: $results"
if ($exit -eq 2) { throw "BLOCKED: Docker Engine, localhost Ollama ou modelo Q4_K_M." }
if ($exit -ne 0) { Write-Warning "Pelo menos uma tentativa falhou; consulte os resultados." }
exit $exit
