# drive-move-check.ps1 -- run after Dropbox moves to a new drive or folder.
# Safe to run any time. It only COPIES Claude memory (never deletes) and otherwise just reports.
#
#   powershell -ExecutionPolicy Bypass -File drive-move-check.ps1
#
# See DRIVE_MOVE.md for what to do with anything it flags.

$ErrorActionPreference = 'Continue'
$Dev = $PSScriptRoot
$issues = 0
function Ok($m)   { Write-Host "  OK    $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  CHECK $m" -ForegroundColor Yellow; $script:issues++ }
function Head($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }

Head "Location"
Write-Host "  Dev folder: $Dev"
$info = Join-Path $env:LOCALAPPDATA 'Dropbox\info.json'
if (Test-Path $info) {
    $dbx = (Get-Content $info -Raw | ConvertFrom-Json).personal.path
    Write-Host "  Dropbox (per Dropbox app): $dbx"
    if ($Dev -notlike "$dbx*") { Warn "Dev folder is not inside the Dropbox folder Dropbox reports" }
} else { Warn "Dropbox info.json not found - is Dropbox installed and signed in?" }

# 1. Claude memory is stored per folder path, so a new path starts with an empty memory.
Head "Claude memory"
$projects = Join-Path $env:USERPROFILE '.claude\projects'
$curKey = ($Dev -replace '[^A-Za-z0-9]', '-')
$curMem = Join-Path $projects "$curKey\memory"
New-Item -ItemType Directory -Force $curMem | Out-Null
$copied = 0
Get-ChildItem $projects -Directory -Filter '*Dropbox-J-Feels-Dev' | Where-Object { $_.Name -ne $curKey } | ForEach-Object {
    $src = Join-Path $_.FullName 'memory'
    if (Test-Path $src) {
        Get-ChildItem $src -File | ForEach-Object {
            $dst = Join-Path $curMem $_.Name
            if (-not (Test-Path $dst) -or $_.LastWriteTime -gt (Get-Item $dst).LastWriteTime) {
                Copy-Item $_.FullName $dst -Force; $copied++
            }
        }
    }
}
$memCount = (Get-ChildItem $curMem -File).Count
if ($copied) { Ok "copied $copied memory file(s) from old path(s); $memCount now at $curKey" }
elseif ($memCount) { Ok "$memCount memory files already at $curKey" }
else { Warn "no memory files found anywhere - check $projects" }
# Point the notes at the new location (any drive letter / user folder -> current).
$devFwd = $Dev -replace '\\', '/'
Get-ChildItem $curMem -Filter *.md | ForEach-Object {
    $s = [IO.File]::ReadAllText($_.FullName)
    $n = [regex]::Replace($s, '[A-Za-z]:[\\/](?:[^\\/\r\n`"'']+[\\/])*?Dropbox[\\/]J Feels[\\/]Dev', {
        param($m) if ($m.Value -match '/') { $devFwd } else { $Dev } })
    if ($n -ne $s) { [IO.File]::WriteAllText($_.FullName, $n, (New-Object Text.UTF8Encoding($false))); Ok "updated paths in memory\$($_.Name)" }
}

# 2. Hardcoded Dev paths that point somewhere other than here.
Head "Hardcoded old paths in files"
$pattern = '[A-Za-z]:[\\/]+(?:[^\\/\r\n"''`]+[\\/]+)*?Dropbox[\\/]+J Feels[\\/]+Dev'
$skipDir = '\\(node_modules|\.git|__pycache__|dist|logs|downloads|archive|data|output)\\'
$hits = Get-ChildItem $Dev -Recurse -File -Include *.py, *.js, *.mjs, *.bat, *.cmd, *.ps1, *.md, *.json, *.yml, *.yaml, *.gs, *.sh, *.env -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch $skipDir -and $_.Name -notmatch '\.tmp\.' -and $_.Name -ne 'drive-move-check.ps1' -and $_.Length -lt 2MB } |
    Select-String -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue |
    Where-Object { $_.Matches | Where-Object { ($_.Value -replace '/', '\') -ne $Dev } }
if ($hits) { $hits | ForEach-Object { Warn ("{0}:{1}  {2}" -f $_.Path.Substring($Dev.Length + 1), $_.LineNumber, $_.Line.Trim()) } }
else { Ok "no files point at an old Dev location" }

# 3. Secrets that live only on disk (gitignored, so GitHub can't restore them).
Head "Local secret files"
foreach ($f in 'foreclosure-agent\credentials.json', 'foreclosure-agent\.env', 'seo-agent\.env',
               'acquisition-trainer\backend\.env', 'lis-pendens-agent\credentials.json', 'lis-pendens-agent\token.json') {
    if (Test-Path (Join-Path $Dev $f)) { Ok $f } else { Warn "$f is missing" }
}
foreach ($f in "$env:USERPROFILE\.olc_key") { if (Test-Path $f) { Ok $f } else { Warn "$f is missing (Open Letter Connect key copy)" } }

# 4. Windows scheduled tasks. All are DISABLED on purpose: GitHub Actions runs these jobs now.
Head "Windows scheduled tasks (should stay Disabled)"
Get-ScheduledTask | Where-Object { $_.TaskName -match 'Buying ?Hero' -and $_.TaskName -ne 'BuyingHeroGitHubRunner' } | ForEach-Object {
    $exe = ("$($_.Actions[0].Execute) $($_.Actions[0].Arguments)").Trim().Replace('"', '')
    $state = $_.State
    if ($state -ne 'Disabled') { Warn "$($_.TaskName) is $state - it would double-run a GitHub job" }
    elseif (-not (Test-Path $exe)) { Warn "$($_.TaskName) points at a missing path: $exe" }
    else { Ok "$($_.TaskName) (Disabled, path valid)" }
}

# 5. Nested git repos inside Dropbox.
Head "Git repos inside Dev"
foreach ($r in 'acquisition-trainer', 'yt-intel-dashboard') {
    $p = Join-Path $Dev $r
    if (-not (Test-Path "$p\.git")) { Warn "$r has no .git (clone fresh from GitHub if you need git there)"; continue }
    $dirty = @(git -C $p status --porcelain 2>$null | Where-Object { $_ -notmatch 'timestamp-|supabase/\.temp|update\.finished' }).Count
    if ($dirty) { Warn "$r has $dirty uncommitted change(s) - push them" } else { Ok "$r clean" }
}

# 6. The cloud side (does not depend on this PC, but confirms nothing else broke).
Head "Cloud automations"
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $runs = gh run list -R jfeelio/buying-hero-bot -L 40 --json workflowName,conclusion,createdAt 2>$null | ConvertFrom-Json
    $since = (Get-Date).ToUniversalTime().AddHours(-36)
    $bad = $runs | Where-Object { [datetime]$_.createdAt -gt $since -and $_.conclusion -in 'failure', 'startup_failure' }
    if ($bad) { $bad | ForEach-Object { Warn "GitHub: $($_.workflowName) failed $($_.createdAt)" } }
    elseif ($runs) { Ok "GitHub Actions: no failures in the last 36h" } else { Warn "could not read GitHub runs (run: gh auth login)" }
} else { Warn "gh CLI not installed" }
try { $code = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 15 https://automations.buyinghero.com/healthz).StatusCode; Ok "n8n server up (HTTP $code)" }
catch { Warn "n8n server did not answer: $($_.Exception.Message)" }

Write-Host ""
if ($issues) { Write-Host "$issues item(s) to check - see DRIVE_MOVE.md" -ForegroundColor Yellow }
else { Write-Host "All clear." -ForegroundColor Green }
