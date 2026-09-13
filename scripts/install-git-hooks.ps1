<#
.SYNOPSIS
    Installs (or removes) the repository-managed git hooks by pointing core.hooksPath at .githooks.

.DESCRIPTION
    Git only runs hooks from a single directory. By default that is the shared .git/hooks folder,
    which is not tracked in version control. This script sets `core.hooksPath` to the tracked
    `.githooks` directory so every contributor and every agent worktree runs the same
    secret-scanning pre-commit gate.

    The path is stored RELATIVE (".githooks"). Git resolves a relative core.hooksPath against the
    top level of the working tree the hook is running in, so one setting correctly resolves to
    each worktree's own copy of .githooks.

.NOTES
    SCOPE WARNING - READ BEFORE RUNNING

    core.hooksPath is stored in the repository config, and the primary clone plus every
    `git worktree` slot (worktrees/wt-01 .. wt-05) SHARE ONE .git directory and therefore ONE
    config. Running this script changes the commit behaviour of every slot immediately, including
    slots where another agent is mid-task.

    Do not run this while parallel agent work is in flight. The orchestrator activates the hook
    once the agent branches have merged.

    See docs/agent-worktree-security.md for the layered security model this hook belongs to.

.PARAMETER Uninstall
    Unsets core.hooksPath, restoring git's default .git/hooks behaviour.

.PARAMETER Force
    Overwrite an existing core.hooksPath that points somewhere other than .githooks.

.EXAMPLE
    pwsh -File scripts/install-git-hooks.ps1
    Installs the hooks for the primary clone and every worktree.

.EXAMPLE
    pwsh -File scripts/install-git-hooks.ps1 -Uninstall
    Removes the setting.

.EXAMPLE
    git config --get core.hooksPath
    Verifies the current state by hand. No output means the hooks are not installed.
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HooksPathValue = '.githooks'

function Get-HooksPath {
    $value = & git config --get core.hooksPath
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) { return $null }
    return $value.Trim()
}

# --- locate the repository -------------------------------------------------
$commonDir = & git rev-parse --git-common-dir
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Not inside a git repository. Run this from the repo (or any worktree of it).'
    exit 1
}

$topLevel = (& git rev-parse --show-toplevel).Trim()
Write-Host "Repository working tree : $topLevel"
Write-Host "Shared git directory    : $((Resolve-Path $commonDir).Path)"
Write-Host ''

# --- uninstall -------------------------------------------------------------
if ($Uninstall) {
    $current = Get-HooksPath
    if ($null -eq $current) {
        Write-Host 'core.hooksPath is already unset. Nothing to do.'
        exit 0
    }

    & git config --unset-all core.hooksPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Failed to unset core.hooksPath.'
        exit 1
    }

    if ($null -ne (Get-HooksPath)) {
        Write-Error 'core.hooksPath is still set after --unset-all. Check for an include/global override.'
        exit 1
    }

    Write-Host "Removed core.hooksPath (was '$current')."
    Write-Host 'Git has reverted to the default .git/hooks directory for the primary clone and'
    Write-Host 'every worktree. The pre-commit secret scan is NO LONGER enforced locally.'
    exit 0
}

# --- preflight -------------------------------------------------------------
$hooksDir = Join-Path $topLevel $HooksPathValue
$preCommit = Join-Path $hooksDir 'pre-commit'

if (-not (Test-Path -LiteralPath $preCommit -PathType Leaf)) {
    Write-Error "Expected hook not found: $preCommit. Are you on a branch that contains .githooks/?"
    exit 1
}

$current = Get-HooksPath
if ($null -ne $current -and $current -ne $HooksPathValue -and -not $Force) {
    Write-Error "core.hooksPath is already set to '$current'. Re-run with -Force to replace it, or -Uninstall to clear it."
    exit 1
}

if ($current -eq $HooksPathValue) {
    Write-Host "core.hooksPath is already '$HooksPathValue'. Already installed; nothing changed."
}
else {
    & git config core.hooksPath $HooksPathValue
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Failed to set core.hooksPath.'
        exit 1
    }
    Write-Host "Set core.hooksPath = $HooksPathValue"
}

# --- verify ----------------------------------------------------------------
$verified = Get-HooksPath
if ($verified -ne $HooksPathValue) {
    Write-Error "Verification failed: core.hooksPath reads back as '$verified'."
    exit 1
}
Write-Host "Verified: git config --get core.hooksPath -> $verified"
Write-Host ''

# --- report scope ----------------------------------------------------------
Write-Host 'Scope of this setting:'
Write-Host '  core.hooksPath lives in the shared repository config. The primary clone and every'
Write-Host '  git worktree share one .git directory, so this single setting now governs commits in'
Write-Host '  ALL of the following working trees:'
Write-Host ''

$worktrees = @()
foreach ($line in (& git worktree list --porcelain)) {
    if ($line -like 'worktree *') { $worktrees += $line.Substring(9) }
}
foreach ($wt in $worktrees) {
    $hasHook = Test-Path -LiteralPath (Join-Path $wt '.githooks/pre-commit') -PathType Leaf
    $mark = if ($hasHook) { 'hook present' } else { 'NO .githooks on its checked-out branch' }
    Write-Host ("    {0,-70} {1}" -f $wt, $mark)
}

Write-Host ''
Write-Host 'A worktree listed above WITHOUT .githooks on its branch will silently run no hooks,'
Write-Host 'because a missing hooks directory is not an error to git. Merge .githooks into every'
Write-Host 'active branch for full coverage.'
Write-Host ''
Write-Host 'Test it (in a scratch branch):'
Write-Host '    printf ''aws_access_key_id = "AKIA<16 fake chars>"'' > scratch.txt'
Write-Host '    git add scratch.txt && git commit -m "should be blocked"'
Write-Host ''
Write-Host 'Deliberate override for a confirmed false positive:  git commit --no-verify'
