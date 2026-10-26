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
& python -B -m unittest discover -s $dir -p 'test_relay_*.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Contrato da ponte Ollama falhou; nao iniciar Docker.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker ausente." }
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop indisponivel." }
if (Test-Path (Join-Path $results "report.json")) { throw "Use uma pasta de saida nova." }
New-Item -ItemType Directory -Force -Path $results | Out-Null
# Hardware attestation only: no host/user identifiers, no inference and no secrets.
$cpuName = "UNKNOWN"
$ramBytes = $null
$gpuInventory = @()
try {
  $cpuName = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name).Trim()
  $ramBytes = [long](Get-CimInstance Win32_ComputerSystem | Select-Object -ExpandProperty TotalPhysicalMemory)
} catch { Write-Warning "Hardware CPU/RAM inventory unavailable." }
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  $gpuInventory = @(& nvidia-smi '--query-gpu=name,memory.total,driver_version' '--format=csv,noheader,nounits')
  if ($LASTEXITCODE -ne 0) { $gpuInventory = @() }
}
$hardware = [ordered]@{
  schema = 1
  collected_at_utc = [DateTime]::UtcNow.ToString("o")
  os = "Windows"
  cpu = $cpuName
  ram_bytes = $ramBytes
  gpu_nvidia_name_memory_mib_driver_csv = $gpuInventory
  gpu_telemetry = "inventory_only; no VRAM peak claim"
}
$hardware | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $results 'hardware.json') -Encoding UTF8
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
