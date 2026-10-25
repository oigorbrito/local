# LOCAL-17: one controlled Windows trial; no automatic retry or patch application.
# Run from any PowerShell directory. Requires a clean frozen issue worktree and a task file.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$IssueRepo,
    [Parameter(Mandatory=$true)][string]$TaskFile,
    [Parameter(Mandatory=$true)][string]$Session,
    [switch]$AuthorizeOneModelCall,
    [string]$ExpectedTaskSha256,
    [int]$TimeoutSeconds = 180
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$workflow = Join-Path $PSScriptRoot 'local16_workflow.py'
function Assert-True([bool]$condition, [string]$reason) {
    if (-not $condition) { throw $reason }
}
function Invoke-Git([string[]]$gitArgs) {
    $out = & git -C $IssueRepo @gitArgs 2>&1
    Assert-True ($LASTEXITCODE -eq 0) "GIT_PREFLIGHT_FAILED"
    return ($out | Out-String).Trim()
}
function Invoke-Workflow([string[]]$workflowArgs) {
    $output = & python $workflow @workflowArgs 2>&1
    $exitCode = $LASTEXITCODE
    $lines = @($output | ForEach-Object { "$_" })
    $last = $lines | Where-Object { $_.Trim().StartsWith('{') } | Select-Object -Last 1
    Assert-True (-not [string]::IsNullOrWhiteSpace($last)) "WORKFLOW_JSON_MISSING"
    $result = $last | ConvertFrom-Json
    return [pscustomobject]@{ExitCode=$exitCode; Result=$result}
}
Assert-True (Test-Path -LiteralPath $workflow -PathType Leaf) 'WORKFLOW_NOT_FOUND'
Assert-True (Test-Path -LiteralPath $TaskFile -PathType Leaf) 'TASK_FILE_NOT_FOUND'
Assert-True (Test-Path -LiteralPath $IssueRepo -PathType Container) 'ISSUE_REPO_NOT_FOUND'
Assert-True ($TimeoutSeconds -ge 1 -and $TimeoutSeconds -le 420) 'INVALID_TIMEOUT'
$expected = 'a3e80e82788d798faa1a83b5a99762412cdaf61b'
$head = Invoke-Git -gitArgs @('rev-parse','HEAD')
Assert-True ($head -eq $expected) 'FROZEN_ISSUE_COMMIT_DRIFT'
$dirty = Invoke-Git -gitArgs @('status','--porcelain')
Assert-True ([string]::IsNullOrEmpty($dirty)) 'FROZEN_ISSUE_WORKTREE_DIRTY'
Assert-True (-not (Test-Path -LiteralPath $Session)) 'SESSION_ALREADY_EXISTS_NO_RETRY'
$parent = Split-Path -Parent $Session
Assert-True (Test-Path -LiteralPath $parent -PathType Container) 'SESSION_PARENT_MISSING'
$taskHash = (Get-FileHash -LiteralPath $TaskFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($AuthorizeOneModelCall) {
    Assert-True ($ExpectedTaskSha256 -match '^[0-9a-fA-F]{64}
$pre = [ordered]@{gate='LOCAL17_ONE_SHOT'; source_commit=$head; task_sha256=$taskHash; session=$Session; model_call_authorized=[bool]$AuthorizeOneModelCall}
$pre | ConvertTo-Json -Compress
if (-not $AuthorizeOneModelCall) {
    Write-Output '{"status":"PREFLIGHT_ONLY","inference_calls_attempted":0}'
    exit 0
}
$created = Invoke-Workflow -workflowArgs @('new','--repo',$IssueRepo,'--session',$Session,'--profile','principal','--task-file',$TaskFile)
Assert-True ($created.ExitCode -eq 0 -and $created.Result.status -eq 'SESSION_PREPARED') 'SESSION_CREATION_FAILED'
# Exactly one explicit generate invocation. Never retry on failure.
$generation = Invoke-Workflow -workflowArgs @('generate','--session',$Session,'--timeout',"$TimeoutSeconds")
$observed = Invoke-Workflow -workflowArgs @('status','--session',$Session)
$summary = [ordered]@{
    gate='LOCAL17_ONE_SHOT_RESULT'
    generate_exit_code=$generation.ExitCode
    generation=$generation.Result
    status=$observed.Result
    session=$Session
    source_commit_after=(Invoke-Git -gitArgs @('rev-parse','HEAD'))
    source_dirty_after=(Invoke-Git -gitArgs @('status','--porcelain'))
    no_automatic_retry=$true
    no_patch_application=$true
}
$summary | ConvertTo-Json -Depth 12
if ($generation.ExitCode -ne 0 -or $observed.ExitCode -ne 0) { exit 2 }
if ($summary.source_commit_after -ne $expected -or $summary.source_dirty_after) { exit 3 }
) 'EXPECTED_TASK_HASH_REQUIRED'
    Assert-True ($taskHash -eq $ExpectedTaskSha256.ToLowerInvariant()) 'FROZEN_TASK_HASH_DRIFT'
}
$pre = [ordered]@{gate='LOCAL17_ONE_SHOT'; source_commit=$head; task_sha256=$taskHash; session=$Session; model_call_authorized=[bool]$AuthorizeOneModelCall}
$pre | ConvertTo-Json -Compress
if (-not $AuthorizeOneModelCall) {
    Write-Output '{"status":"PREFLIGHT_ONLY","inference_calls_attempted":0}'
    exit 0
}
$created = Invoke-Workflow -workflowArgs @('new','--repo',$IssueRepo,'--session',$Session,'--profile','principal','--task-file',$TaskFile)
Assert-True ($created.ExitCode -eq 0 -and $created.Result.status -eq 'SESSION_PREPARED') 'SESSION_CREATION_FAILED'
# Exactly one explicit generate invocation. Never retry on failure.
$generation = Invoke-Workflow -workflowArgs @('generate','--session',$Session,'--timeout',"$TimeoutSeconds")
$observed = Invoke-Workflow -workflowArgs @('status','--session',$Session)
$summary = [ordered]@{
    gate='LOCAL17_ONE_SHOT_RESULT'
    generate_exit_code=$generation.ExitCode
    generation=$generation.Result
    status=$observed.Result
    session=$Session
    source_commit_after=(Invoke-Git -gitArgs @('rev-parse','HEAD'))
    source_dirty_after=(Invoke-Git -gitArgs @('status','--porcelain'))
    no_automatic_retry=$true
    no_patch_application=$true
}
$summary | ConvertTo-Json -Depth 12
if ($generation.ExitCode -ne 0 -or $observed.ExitCode -ne 0) { exit 2 }
if ($summary.source_commit_after -ne $expected -or $summary.source_dirty_after) { exit 3 }
