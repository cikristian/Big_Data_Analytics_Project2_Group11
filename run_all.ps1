<#
  Runs the whole project from the beginning, in submission order, and pauses
  at every point where the handout needs a screenshot. Every step's output is
  also saved to results\logs\<step>.txt (useful evidence and for debugging).

  HOW TO RUN (PowerShell opened with "Run as administrator", so the script can
  stop/start the PostgreSQL service for the one-engine-at-a-time timings):

      cd "C:\Users\Christian\OneDrive\Desktop\AUCA_Masters\Big_Data_Analytics\Big_Data_Analytics_Project2_Group11"
      .\.venv\Scripts\Activate.ps1
      Set-ExecutionPolicy -Scope Process Bypass -Force
      .\run_all.ps1 -PgPassword 1234 -NeoPassword 12345678

  If a step fails, fix the problem and continue from that phase, e.g.:
      .\run_all.ps1 -PgPassword 1234 -NeoPassword 12345678 -From 5
  Use -NoPause to run without stopping for screenshots.
#>
param(
    [Parameter(Mandatory)] [string] $PgPassword,
    [Parameter(Mandatory)] [string] $NeoPassword,
    [int]    $From = 1,
    [string] $DataDir = "C:\mm_work\data",
    [string] $NeoRoot = "C:\neo4j",
    [string] $NeoVersion = "2026.09.0",
    [switch] $NoPause
)

$ErrorActionPreference = "Continue"
$Proj   = $PSScriptRoot
Set-Location $Proj
$LogDir = Join-Path $Proj "results\logs"
New-Item -ItemType Directory -Force $LogDir, $DataDir | Out-Null

# ----------------------------------------------------------------- environment
$env:PGPASSWORD        = $PgPassword
$env:MM_PG_DSN         = "host=localhost port=5432 dbname=mobile_money user=postgres password=$PgPassword"
$env:MM_NEO4J_PASSWORD = $NeoPassword
$env:MM_DATA_DIR       = $DataDir
$env:PYTHONUNBUFFERED  = "1"

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    $pgBin = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
             Sort-Object FullName -Descending | Select-Object -First 1
    if ($pgBin) { $env:Path = "$($pgBin.DirectoryName);$env:Path" } else { throw "psql not found" }
}

function Get-JavaMajor([string]$exe) {
    $v = (& $exe -version 2>&1 | Out-String)
    if ($v -match 'version "(\d+)') { return [int]$Matches[1] } else { return 0 }
}

function Use-Java21 {
    $candidates = @()
    if ($env:JAVA_HOME) { $candidates += Join-Path $env:JAVA_HOME "bin\java.exe" }
    $cmd = Get-Command java -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    foreach ($root in "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java", "C:\Program Files\Microsoft",
                      "$HOME\.Neo4jDesktop2", "C:\Program Files\Neo4j Desktop 2") {
        if (Test-Path $root) {
            $candidates += Get-ChildItem $root -Filter java.exe -Recurse -ErrorAction SilentlyContinue |
                           Select-Object -ExpandProperty FullName
        }
    }
    foreach ($exe in ($candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)) {
        if ((Get-JavaMajor $exe) -eq 21) {
            $env:JAVA_HOME = Split-Path (Split-Path $exe)
            $env:Path = "$env:JAVA_HOME\bin;$env:Path"
            Write-Host "Using Java 21: $env:JAVA_HOME" -ForegroundColor Green
            return
        }
    }
    throw "No Java 21 found. Install Temurin JDK 21 (adoptium.net), reopen PowerShell, rerun."
}

function Use-Neo4j {
    $home_ = Get-ChildItem $NeoRoot -Directory -Filter "neo4j-community-*" -ErrorAction SilentlyContinue |
             Sort-Object Name -Descending | Select-Object -First 1
    if (-not $home_) {
        Write-Host "Downloading Neo4j Community $NeoVersion ..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Force $NeoRoot | Out-Null
        $zip = Join-Path $NeoRoot "neo4j.zip"
        Invoke-WebRequest "https://dist.neo4j.org/neo4j-community-$NeoVersion-windows.zip" -OutFile $zip
        Expand-Archive $zip -DestinationPath $NeoRoot -Force
        Remove-Item $zip
        $home_ = Get-ChildItem $NeoRoot -Directory -Filter "neo4j-community-*" | Select-Object -First 1
    }
    $env:NEO4J_HOME = $home_.FullName
    Write-Host "NEO4J_HOME = $env:NEO4J_HOME" -ForegroundColor Green
}

function Test-Port([int]$port) {
    try { $c = New-Object Net.Sockets.TcpClient; $ok = $c.ConnectAsync("127.0.0.1", $port).Wait(1000); $c.Close(); return $ok }
    catch { return $false }
}

function Stop-Neo4j {
    Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
        Where-Object { $_.CommandLine -like "*neo4j-community*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep 3
    if (Test-Port 7687) {
        Write-Host "Port 7687 is still in use - close Neo4j Desktop (or its running DBMS)." -ForegroundColor Red
        Read-Host "Press Enter once it is closed"
    }
    Write-Host "Neo4j stopped." -ForegroundColor Green
}

function Start-Neo4j {
    if (Test-Port 7687) { Write-Host "Neo4j already running."; return }
    Start-Process -FilePath (Join-Path $env:NEO4J_HOME "bin\neo4j.bat") -ArgumentList "console" `
                  -WorkingDirectory $env:NEO4J_HOME
    Write-Host "Starting Neo4j in a new window ..." -NoNewline
    for ($i = 0; $i -lt 240; $i++) {
        try { Invoke-WebRequest "http://localhost:7474" -UseBasicParsing -TimeoutSec 2 | Out-Null
              if (Test-Port 7687) { Start-Sleep 5; Write-Host " ready." -ForegroundColor Green; return } }
        catch { }
        Write-Host "." -NoNewline; Start-Sleep 2
    }
    throw "Neo4j did not start - look at the Neo4j window for the error."
}

function Get-PgService { Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1 }

function Stop-Pg {
    $s = Get-PgService
    try { Stop-Service $s.Name -ErrorAction Stop } catch {
        Write-Host "Could not stop PostgreSQL automatically (run PowerShell as administrator)." -ForegroundColor Red
        Write-Host "Open services.msc, stop '$($s.DisplayName)'." -ForegroundColor Yellow
        Read-Host "Press Enter once it is stopped"
    }
    Start-Sleep 2
    Write-Host "PostgreSQL running: $(Test-Port 5432)"
}

function Start-Pg {
    if (Test-Port 5432) { return }
    $s = Get-PgService
    try { Start-Service $s.Name -ErrorAction Stop } catch {
        Write-Host "Start '$($s.DisplayName)' in services.msc." -ForegroundColor Yellow
        Read-Host "Press Enter once it is running"
    }
    for ($i = 0; $i -lt 30 -and -not (Test-Port 5432); $i++) { Start-Sleep 1 }
    Write-Host "PostgreSQL running: $(Test-Port 5432)"
}

function Run([string]$name, [scriptblock]$block) {
    $log = Join-Path $LogDir "$name.txt"
    Write-Host "`n==================== $name ====================" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $block 2>&1 | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nSTEP FAILED: $name (exit $LASTEXITCODE). Output saved in $log" -ForegroundColor Red
        Write-Host "Fix it, then rerun this script with -From $script:Phase" -ForegroundColor Red
        exit 1
    }
}

function Shot([string]$what) {
    Write-Host "`n>>> SCREENSHOT: $what" -ForegroundColor Yellow
    if (-not $NoPause) { Read-Host "    Take it, then press Enter to continue" | Out-Null }
}

Use-Java21
Use-Neo4j

# ----------------------------------------------------------------------- phases
$phases = [ordered]@{
  1 = { # Generator + capture (1.2)
        Run "01_verify_generator" { python verify_generator.py }
        Run "02_capture_preview"  { python capture.py --preview }
        Shot "capture.py --preview: dataset_info, FIELDS and ten rows per stream (section 1.2)"
        Run "03_capture_full"     { python capture.py }
        Shot "capture totals: 20,993,500 records, transfer audit, seconds, GB (section 1.2)" }

  2 = { # PostgreSQL schema + load + constraints + checks (2.1-2.2)
        Start-Pg
        $exists = psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='mobile_money'"
        if ("$exists".Trim() -ne "1") { Run "04_create_db" { psql -U postgres -c "CREATE DATABASE mobile_money" } }
        Run "05_pg_schema" { psql -U postgres -d mobile_money -f "$Proj\sql\01_schema.sql" }
        Push-Location (Split-Path $DataDir)
        Run "06_pg_load" { psql -U postgres -d mobile_money -f "$Proj\sql\02_load.sql" }
        Pop-Location
        Shot "PostgreSQL load: COPY counts (last one 20003300) and Time lines (section 2.2)"
        Run "07_pg_constraints_indexes" { psql -U postgres -d mobile_money -f "$Proj\sql\03_constraints_indexes.sql" }
        Shot "constraint/index setup: SETUP START and SETUP END times (section 2.2)"
        Run "08_pg_table_definitions" {
            foreach ($t in "customers","accounts","devices","account_devices","transfers") {
                psql -U postgres -d mobile_money -c "\d+ $t" } }
        Shot "table definitions \d+ (section 2.1)"
        Run "09_pg_checks" { psql -U postgres -d mobile_money -f "$Proj\sql\04_checks.sql" }
        Shot "PostgreSQL checks: counts, audit, roles, constraints validated, indexes, GB (section 2.2)" }

  3 = { # Neo4j import (3.2)
        Stop-Neo4j
        foreach ($d in "databases","transactions","dbms") {
            Remove-Item (Join-Path $env:NEO4J_HOME "data\$d") -Recurse -Force -ErrorAction SilentlyContinue }
        $conf = Join-Path $env:NEO4J_HOME "conf\neo4j.conf"
        if (-not (Select-String -Path $conf -Pattern '^server\.memory\.heap\.max_size' -Quiet)) {
            Add-Content $conf "`nserver.memory.heap.initial_size=2g`nserver.memory.heap.max_size=2g`nserver.memory.pagecache.size=3g" }
        Run "10_neo_password" { & (Join-Path $env:NEO4J_HOME "bin\neo4j-admin.bat") dbms set-initial-password $NeoPassword }
        Run "11_neo_import" { python prepare_import.py --run }
        Shot "Neo4j import summary + 'Import finished in ... s' (section 3.2)" }

  4 = { # Neo4j setup + checks + account trace (3.2, 3.3, 1.1)
        Start-Neo4j
        Shot "Neo4j console window showing 'Started.'"
        Run "12_neo_setup"  { python neo4j_checks.py --setup }
        Shot "constraints and TRANSFER.occurred_at index ONLINE + setup seconds (section 3.2)"
        Run "13_neo_checks" { python neo4j_checks.py }
        Shot "Neo4j checks: node/relationship counts, roles, owners, unique transfer_id, audit, sizes (section 3.2)"
        Run "14_neo_cleanup" { python prepare_import.py --cleanup }
        Run "15_env_info"    { python env_info.py }
        Shot "environment: versions, CPU, RAM, OS, memory settings, both connections OK (section 1.1)"
        Run "16_inspect_account" { python inspect_account.py 998 }
        Shot "account 998 traced in both models (section 3.3)" }

  5 = { # Correctness (6.1) + answers (4, 5)
        Start-Pg; Start-Neo4j
        Run "17_reference"        { python reference.py }
        Run "18_compare_baseline" { python compare.py }
        Shot "61-case comparison table, Q7 path checks and '61/61 cases match' (section 6.1)"
        Run "19_verify_csv"       { python verify_csv.py }
        Shot "independent CSV checks: device overlap, chain, cycle (section 6.1)"
        foreach ($q in "Q1","Q2","Q3","Q4","Q5","Q6","Q7") {
            Run "20_answers_$q" { python show_answers.py $q }
            Shot "$q results (sections 4-5)" } }

  6 = { # PostgreSQL timing with Neo4j stopped (6.2, 6.3, 7.1)
        Stop-Neo4j; Start-Pg
        Write-Host "Close other heavy apps, keep the laptop plugged in, pause OneDrive sync." -ForegroundColor Yellow
        Run "21_bench_pg"         { python benchmark.py --engine pg }
        Run "22_bench_pg_q7bidir" { python benchmark.py --engine pg --q7 bidir --only Q7 }
        Run "23_plans_pg"         { python plans.py --engine pg }
        Shot "PostgreSQL plans for Q2, Q4 B d10, Q7 B b6 baseline and improved (sections 6.2-6.3)"
        Write-Host "Open Task Manager (Performance tab) now. Screenshot it while the 16-client runs are going." -ForegroundColor Yellow
        Run "24_load_pg"          { python loadtest.py --engine pg --q7 bidir }
        Shot "Task Manager during a 16-client PostgreSQL run (section 7.1)" }

  7 = { # Neo4j timing with PostgreSQL stopped
        Stop-Pg; Start-Neo4j
        Run "25_bench_neo" { python benchmark.py --engine neo }
        Run "26_plans_neo" { python plans.py --engine neo }
        Shot "Neo4j PROFILE output for Q2, Q4 B d10, Q7 B b6 (section 6.2)"
        Write-Host "Open Task Manager again for the 16-client Neo4j runs." -ForegroundColor Yellow
        Run "27_load_neo"  { python loadtest.py --engine neo }
        Shot "Task Manager during a 16-client Neo4j run (section 7.1)" }

  8 = { # Summaries, recheck, charts (6.2, 6.3, 7.2, 9.2)
        Start-Pg; Start-Neo4j
        Run "28_bench_summary" { python benchmark.py --summary }
        Shot "timing summary: median/min/max per case and PG/Neo ratio (section 6.2)"
        Run "29_load_summary"  { python loadtest.py --summary }
        Shot "load-test summary: throughput, median, p95, errors per engine/workload/clients (section 7.1)"
        Run "30_compare_final" { python compare.py --q7 bidir }
        Shot "FINAL 61-case comparison with the submitted SQL: '61/61 cases match' (sections 6.3 and 9.2)"
        Run "31_answers_q7_final" { python show_answers.py Q7 }
        Run "32_plots" { python plots.py }
        Start-Process (Join-Path $Proj "results\charts")
        Write-Host "Charts opened: insert them in the report (no screenshot needed)." }

  9 = { # Shut down (9.2)
        Stop-Neo4j; Stop-Pg
        Run "33_services_stopped" {
            Get-Service -Name "postgresql*" | Format-Table Name, Status
            "Neo4j bolt port 7687 open: $(Test-Port 7687)"
            "PostgreSQL port 5432 open: $(Test-Port 5432)" }
        Shot "both services stopped (section 9.2)"
        Write-Host "`nALL DONE. Logs are in results\logs, charts in results\charts." -ForegroundColor Green }
}

foreach ($k in $phases.Keys) {
    if ($k -lt $From) { continue }
    $script:Phase = $k
    Write-Host "`n########## PHASE $k ##########" -ForegroundColor Magenta
    & $phases[$k]
}
