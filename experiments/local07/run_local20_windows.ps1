# LOCAL-20: one Windows command, one frozen local Nemotron attempt.
# No mutation of the user's main checkout, retries, candidate execution or merges.
[CmdletBinding()]
param(
    [ValidateRange(1, 420)]
    [int]$Timeout = 300,
    [string]$EvidenceDirectory = (Join-Path $env:LOCALAPPDATA "LOCAL-20")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remote = "https://github.com/oigorbrito/local.git"
$runnerBranch = "feat/local20-one-command-gates"
# The pinned runner was green on Ubuntu and Windows in CI, run 40259967110.
$runnerCommit = "8fe0b095c40bde811f1127d62aafdea92db63896"
$caseId = "oigorbrito__local-anchor-separation-002"
$caseHead = "11fd231cf2ebd27151b1390621c61dd2cf7a1af5"
$caseBlob = "ce1d7b4a37d73e1f595645d759542ba478991898"
$taskSha = "058509e618b98848a34880805a4aad1a97cfc42c6d0c65413243af3ff6cc6261"
$taskGitPath = "experiments/local07/cases/anchor-reasons-002.txt"
$target = "experiments/local07/executor_bridge.py"

function Require-ExitZero([string]$step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$step failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "GIT_NOT_FOUND" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "PYTHON_NOT_FOUND" }
# Create a unique evidence directory; never overwrite existing trials.
$base = [System.IO.Path]::GetFullPath($EvidenceDirectory)
New-Item -ItemType Directory -Path $base -Force | Out-Null
$root = Join-Path $base ("anchor-002-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
$runner = Join-Path $root "runner"
$trial = Join-Path $root "pinned-case"
$task = Join-Path $root "task-canonical.txt"
$session = Join-Path $root "session"

Write-Host "LOCAL-20 evidence root: $root"
Write-Host "Cloning the runner into an independent disposable checkout..."
& git clone --quiet --branch $runnerBranch -- $remote $runner
Require-ExitZero "RUNNER_CLONE"
& git -C $runner checkout --quiet --detach $runnerCommit
Require-ExitZero "RUNNER_PIN"
$actualRunner = (& git -C $runner rev-parse HEAD).Trim()
Require-ExitZero "RUNNER_HEAD"
if ($actualRunner -cne $runnerCommit) { throw "RUNNER_COMMIT_MISMATCH" }

& git -C $runner worktree add --quiet --detach $trial $caseHead
Require-ExitZero "FROZEN_CASE_WORKTREE"
$actualHead = (& git -C $trial rev-parse HEAD).Trim()
Require-ExitZero "FROZEN_HEAD"
if ($actualHead -cne $caseHead) { throw "PINNED_HEAD_MISMATCH" }
$actualBlob = (& git -C $trial rev-parse ("HEAD:" + $target)).Trim()
Require-ExitZero "FROZEN_BLOB"
if ($actualBlob -cne $caseBlob) { throw "PINNED_BLOB_MISMATCH" }
$dirty = & git -C $trial status --porcelain
Require-ExitZero "FROZEN_CLEANLINESS"
if ($dirty) { throw "FROZEN_CHECKOUT_DIRTY" }

# PowerShell 5.1 redirection may transcode bytes. Extract the Git blob in
# Python as bytes, validate the frozen digest, then write outside checkout.
$extract = 'import hashlib,pathlib,subprocess,sys; data=subprocess.check_output(["git","-C",sys.argv[1],"show","HEAD:"+sys.argv[3]]); assert hashlib.sha256(data).hexdigest()==sys.argv[4], "PINNED_TASK_MISMATCH"; pathlib.Path(sys.argv[2]).write_bytes(data)'
& python -c $extract $runner $task $taskGitPath $taskSha
Require-ExitZero "CANONICAL_TASK_EXTRACTION"
$actualTaskSha = (Get-FileHash -LiteralPath $task -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualTaskSha -cne $taskSha) { throw "PINNED_TASK_MISMATCH" }

# Persist a per-machine case claim before any possible model call.
# CreateNew is atomic. Even a failed/aborted attempt is not automatically retried.
$claims = Join-Path $base "case-claims"
New-Item -ItemType Directory -Path $claims -Force | Out-Null
$claimPath = Join-Path $claims ($caseId + ".claim")
$claimText = "case=$caseId`nrunner=$runnerCommit`nbase=$caseHead`nevidence=$root`n"
$claimBytes = [System.Text.Encoding]::UTF8.GetBytes($claimText)
try {
    $claimHandle = [System.IO.File]::Open(
        $claimPath, [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::None
    )
} catch [System.IO.IOException] {
    throw "CASE_ALREADY_CLAIMED: $claimPath. Do not repeat a consumed case."
}
try {
    $claimHandle.Write($claimBytes, 0, $claimBytes.Length)
    $claimHandle.Flush()
} finally {
    $claimHandle.Dispose()
}

Write-Host "Executing exactly one LOCAL-20 pipeline invocation..."
& python (Join-Path $runner "experiments/local07/local20_pipeline.py") `
    --repo $trial --session $session --task-file $task `
    --case-id $caseId --expected-head $caseHead `
    --expected-blob $caseBlob --expected-task-sha256 $taskSha `
    --target $target --profile principal-localizado --timeout $Timeout
$exitCode = $LASTEXITCODE

$reportPath = Join-Path $session "pipeline-report.json"
$eventsPath = Join-Path $session "pipeline-events.jsonl"
$responsePath = Join-Path $session "response.json"
$patchPath = Join-Path $session "candidate.patch"
if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
    throw "PIPELINE_REPORT_NOT_FOUND (exit=$exitCode); inspect evidence: $root"
}
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Host "Pipeline status: $($report.status)"
if ($exitCode -ne 0 -or $report.status -cne "PATCH_READY_NOT_FUNCTIONALLY_GRADED") {
    Write-Host "Evidence preserved: $root"
    throw "PIPELINE_BLOCKED; consult $reportPath"
}
if (@($report.events).Count -ne 5 -or @($report.events | Where-Object { $_.status -cne "PASS" }).Count -ne 0) {
    throw "PIPELINE_GATE_REPORT_MISMATCH"
}
if ($report.inference_calls_completed -ne 1 -or $report.functional_resolution -cne "NOT_EVALUATED" -or
    $report.candidate_code_executed -ne $false) {
    throw "PIPELINE_RESULT_INVARIANT_FAILED"
}
foreach ($file in @($eventsPath, $responsePath, $patchPath)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "PIPELINE_ARTIFACT_MISSING: $file"
    }
}
if (@(Get-Content -LiteralPath $eventsPath -Encoding UTF8).Count -ne 5) {
    throw "PIPELINE_EVENT_COUNT_MISMATCH"
}
$responseSha = (Get-FileHash -LiteralPath $responsePath -Algorithm SHA256).Hash.ToLowerInvariant()
$patchSha = (Get-FileHash -LiteralPath $patchPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($responseSha -cne $report.events[3].response_sha256 -or
    $patchSha -cne $report.events[3].patch_sha256 -or
    $patchSha -cne $report.events[4].patch_sha256) {
    throw "PIPELINE_ARTIFACT_HASH_MISMATCH"
}
$finalStatus = (& git -C $trial status --porcelain)
Require-ExitZero "FINAL_SOURCE_STATUS"
if ($finalStatus) { throw "SOURCE_CHECKOUT_MODIFIED" }

Write-Host "Five gates PASS; candidate NOT functionally graded."
Write-Host "response.json SHA-256: $responseSha"
Write-Host "candidate.patch SHA-256: $patchSha"
Write-Host "Evidence preserved: $root"
Write-Host "Next gate: independent isolated functional evaluation (never on this host)."
exit 0
