# NimbusPay v2 merge gate (Windows PowerShell 5.1+ / PowerShell 7). Prints PASS/FAIL per gate and an overall verdict.
#   powershell -ExecutionPolicy Bypass -File parity\verify_parity.ps1 -Fresh https://github.com/<owner>/nimbuspay-adoption-insights -Branch redesign-v2
#   powershell -ExecutionPolicy Bypass -File parity\verify_parity.ps1 -Repo .
# Needs: git, Python 3.12+ (py or python), Node 20+ (npm), Docker Desktop (for G7). Exit 0 only if every gate passes.
param([string]$Repo = ".", [string]$Fresh = "", [string]$Branch = "redesign-v2", [string]$Kit = "", [switch]$NoDocker)
$ErrorActionPreference = "Continue"
if (-not $Kit) { $Kit = $PSScriptRoot }
if ($Fresh) {
  $Repo = Join-Path ([IO.Path]::GetTempPath()) ("np-parity-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
  git clone -q --branch $Branch $Fresh $Repo; if ($LASTEXITCODE -ne 0) { Write-Host "FAIL clone"; exit 1 }
  if (Test-Path (Join-Path $Repo "parity")) { $Kit = Join-Path $Repo "parity" }
}
$Repo = (Resolve-Path $Repo).Path; Set-Location $Repo
$Log = Join-Path ([IO.Path]::GetTempPath()) ("np-parity-log-" + [guid]::NewGuid().ToString("N").Substring(0, 8)); New-Item -ItemType Directory $Log | Out-Null
$Results = [ordered]@{}
function Gate($name, $ok) { $s = if ($ok) { "PASS" } else { "FAIL" }; $Results[$name] = $s; Write-Host "[$s] $name" }
function Tail($f) { (Get-Content $f -Tail 1) -join "" }

# G0 golden file untouched
$expect = (Get-Content (Join-Path $Kit "golden\golden_api.json.sha256") -Raw).Trim()
$actual = (Get-FileHash (Join-Path $Kit "golden\golden_api.json") -Algorithm SHA256).Hash.ToLower()
Gate "G0 golden file untouched" (($actual -eq $expect) -and ($expect -eq "ad0c88df79f1cee32bed2c6ce136b62a1d52e7060fdb44ea24435ef1f6060a9f"))

# G1 install
$sysPy = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
& $sysPy -m venv .venv-parity
$Py = Join-Path $Repo ".venv-parity\Scripts\python.exe"
& $Py -m pip install -q -r requirements.txt -r requirements-dev.txt *> "$Log\pip.log"; $ok1 = $LASTEXITCODE -eq 0
& $Py -m playwright install chromium *> "$Log\pw.log"; Gate "G1 install" ($ok1 -and $LASTEXITCODE -eq 0)

# G2 front-end build
if (Test-Path "web\package.json") {
  Push-Location web; npm ci *> "$Log\npm.log"; $a = $LASTEXITCODE; npm run build *>> "$Log\npm.log"; $b = $LASTEXITCODE; Pop-Location
  Gate "G2 front-end build" (($a -eq 0) -and ($b -eq 0) -and (Test-Path "app\web\index.html"))
} else { Gate "G2 front-end build (no web\ folder: legacy UI only)" $false }

# G3 existing tests: 386 passed + 1 skipped, 0 failed
$core = "tests/test_pipeline.py tests/test_agent.py tests/test_probes.py tests/test_persona.py tests/test_api.py tests/test_features.py tests/test_brain.py tests/test_cost.py tests/test_improvements.py tests/test_break_it.py tests/test_space.py tests/test_finetuned.py tests/test_remote_brain.py tests/test_demo_hardening.py".Split(" ")
& $Py -m pytest -q -p no:cacheprovider @core *> "$Log\pytest.log"
$t = Tail "$Log\pytest.log"
$p = if ($t -match "(\d+) passed") { [int]$Matches[1] } else { 0 }; $s = if ($t -match "(\d+) skipped") { [int]$Matches[1] } else { 0 }
Gate "G3 tests ($t)" ((-not ($t -match "failed|error")) -and (($p + $s) -eq 387) -and ($p -ge 386))

# G4 release gate + break-it
& $Py tools\eval_agent.py --brain rules *> "$Log\eval.log"; $e1 = $LASTEXITCODE
& $Py tools\break_it.py *> "$Log\break.log"; $e2 = $LASTEXITCODE
$ev = Get-Content "$Log\eval.log" -Raw; $bk = Get-Content "$Log\break.log" -Raw
Gate "G4 release gate 21/21 29/29 24/24 40/40, break-it 22/22" (($e1 -eq 0) -and ($e2 -eq 0) -and ($ev -match "Golden 21: 21/21 +Guard\+paraphrase probes: 29/29") -and
  $ev.Contains("panel24: should-answer 17/17, should-refuse 7/7, total 24/24") -and $ev.Contains("extra: should-answer 17/17, should-refuse 23/23, total 40/40") -and
  $bk.Contains("Safe-to-invite set: 15/15 handled correctly; all cases 22/22"))

# G5 golden API on a fresh deterministic server
$port = 7871; $tmp = Join-Path $Log "srv"; New-Item -ItemType Directory $tmp | Out-Null
$envs = @{ HOST = "127.0.0.1"; PORT = "$port"; NP_BRAIN = "rules"; OLLAMA_HOST = "http://127.0.0.1:9"; NP_STREAM_DELAY_MS = "0"; FT_WARMUP = "0";
  AUDIT_DB = "$tmp\audit.db"; NP_FEEDBACK = "$tmp\fb\feedback.jsonl"; NP_EVAL_DIR = "$tmp\evals"; NP_DEMO = "0"; NP_READONLY_PUBLIC = "0"; LLM_API_KEY = ""; OPENAI_API_KEY = ""; FT_REMOTE_URL = "" }
$saved = @{}; foreach ($k in $envs.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envs[$k]) }
$srv = Start-Process -FilePath $Py -ArgumentList "-m", "app" -WorkingDirectory $Repo -PassThru -WindowStyle Hidden -RedirectStandardOutput "$tmp\out.log" -RedirectStandardError "$tmp\err.log"
foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
$up = $false; for ($i = 0; $i -lt 80; $i++) { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/health" -TimeoutSec 2 | Out-Null; $up = $true; break } catch { Start-Sleep -Milliseconds 250 } }
& $Py (Join-Path $Kit "golden.py") check --base "http://127.0.0.1:$port" --root $Repo --golden (Join-Path $Kit "golden") *> "$Log\golden.log"
Gate "G5 golden API ($(Tail "$Log\golden.log"))" ($up -and $LASTEXITCODE -eq 0)

# G6 UI: every-screen smoke (3 widths) + existing Playwright tests
& $Py (Join-Path $Kit "smoke_screens.py") --base "http://127.0.0.1:$port" *> "$Log\smoke.log"; $sm = $LASTEXITCODE
Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
& $Py -m pytest -q -p no:cacheprovider tests/test_ui_playwright.py tests/test_ui_features_playwright.py tests/test_ui_hardening_playwright.py *> "$Log\ui.log"
$u = Tail "$Log\ui.log"; git checkout -q -- docs/screenshots 2>$null
Gate "G6 UI (playwright: $u; $(Tail "$Log\smoke.log"))" (($sm -eq 0) -and ($u -match "^4 passed"))

# G7 Docker on port 7860
if ((-not $NoDocker) -and (Get-Command docker -ErrorAction SilentlyContinue)) {
  docker build -q -t nimbuspay-parity . *> "$Log\docker.log"; $cid = (docker run -d --rm -p 7860:7860 nimbuspay-parity).Trim()
  $ok = $false; for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7860/api/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep 1 } }
  $home_ok = $false; try { $home_ok = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7860/" -TimeoutSec 5).Content.Contains("Adoption Insights") } catch {}
  try { (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7860/api/state" -TimeoutSec 10).Content | Set-Content -Encoding UTF8 "$Log\dstate.json" } catch {}
  $chk = "import json,sys; sys.path.insert(0, sys.argv[3]); import golden as G; w=json.load(open(sys.argv[1],encoding='utf-8'))['state_initial']['response']['json']; g=json.loads(json.dumps(G.norm(json.load(open(sys.argv[2],encoding='utf-8-sig'))),sort_keys=True)); sys.exit(0 if g==w else 1)"
  & $Py -c $chk (Join-Path $Kit "golden\golden_api.json") "$Log\dstate.json" $Kit; $ds = $LASTEXITCODE
  # Docker fix (approved by the project owner): "Explain this number" works (lineage 200) and the Models tab's rules engine row has its 21/21 eval
  $lin = 0; try { $lin = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7860/api/lineage/M01" -TimeoutSec 10).StatusCode } catch {}
  $rl = $false; for ($i = 0; $i -lt 90; $i++) { try { $m = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7860/api/models" -TimeoutSec 10).Content | ConvertFrom-Json; $r = ($m.brains | Where-Object { $_.key -eq "rules" }).result; if ($r -and $r.golden.passed -eq 21 -and $r.golden.total -eq 21) { $rl = $true; break } } catch {}; Start-Sleep 1 }
  docker stop $cid *> $null
  Gate "G7 Docker :7860 health + UI + state + lineage 200 + rules eval 21/21" ($ok -and $home_ok -and ($ds -eq 0) -and ($lin -eq 200) -and $rl)
} else { Gate "G7 Docker :7860 (docker not available: start Docker Desktop and re-run)" $false }

Write-Host ""; Write-Host "Logs: $Log"
$fails = @($Results.Values | Where-Object { $_ -ne "PASS" }).Count
if ($fails -eq 0) { Write-Host "OVERALL: PASS - redesign-v2 may be merged (tag v1-final first)" -ForegroundColor Green; exit 0 }
else { Write-Host "OVERALL: FAIL ($fails gate(s)) - do NOT merge; main stays as-is" -ForegroundColor Red; exit 1 }
