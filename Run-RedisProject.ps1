[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

$RunId = "{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$TempBase = [System.IO.Path]::GetTempPath()
$ArtifactRoot = Join-Path $TempBase "RedisStudentProjectCheck-$RunId"
New-Item -ItemType Directory -Path $ArtifactRoot -Force | Out-Null

$script:Checks = [ordered]@{}
$script:CheckNames = @(
    "Project Files", "Python", "Docker", "Redis", "Redis Python Client", "Memcached", "Database", "Dependencies", "Python Compile",
    "Unit Tests", "Cache-Aside", "Session Storage", "Dashboard", "Benchmark"
)
$script:Failures = @()
$script:BackgroundApps = @()

function Set-Check {
    param(
        [string]$Name,
        [ValidateSet("PASS", "FAIL", "SKIP")][string]$State,
        [string]$Detail
    )
    $script:Checks[$Name] = [pscustomobject]@{ Name = $Name; State = $State; Detail = $Detail }
    $color = switch ($State) { "PASS" { "Green" } "FAIL" { "Red" } default { "Yellow" } }
    Write-Host ("[{0}] {1}: {2}" -f $State, $Name, $Detail) -ForegroundColor $color
    if ($State -eq "FAIL") { $script:Failures += ("{0}: {1}" -f $Name, $Detail) }
}

function Test-LocalPortFree {
    param([int]$Port)
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Get-PortOwnerSummary {
    param([int]$Port)
    $ownerPids = @()
    try {
        $ownerPids = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { }
    $owners = @()
    foreach ($processIdValue in $ownerPids) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processIdValue" -ErrorAction SilentlyContinue
        if ($process) {
            $owners += ("{0} (PID {1})" -f $process.Name, $processIdValue)
        } else {
            $owners += ("PID {0}" -f $processIdValue)
        }
    }
    if ($owners.Count -eq 0) { return "owner process unavailable from TCP table" }
    return ($owners -join ", ")
}

function Invoke-PythonSnippet {
    param(
        [Parameter(Mandatory = $true)][string]$Code,
        [string[]]$Arguments = @()
    )
    $helperPath = Join-Path $ArtifactRoot ("python-helper-{0}.py" -f [guid]::NewGuid().ToString("N"))
    $previousPythonPath = $env:PYTHONPATH
    $workingDirectory = (Get-Location).Path
    try {
        [System.IO.File]::WriteAllText($helperPath, $Code, [System.Text.UTF8Encoding]::new($false))
        if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
            $env:PYTHONPATH = $workingDirectory
        } else {
            $env:PYTHONPATH = $workingDirectory + [System.IO.Path]::PathSeparator + $previousPythonPath
        }
        $output = & $script:VenvPython $helperPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
    } finally {
        $env:PYTHONPATH = $previousPythonPath
        if (Test-Path -LiteralPath $helperPath -PathType Leaf) {
            Remove-Item -LiteralPath $helperPath -Force
        }
    }
}

function Start-ProjectWebApp {
    param(
        [string]$Name,
        [string]$Module,
        [int]$Port,
        [string]$Url
    )
    if (-not (Test-LocalPortFree -Port $Port)) {
        $ownerSummary = Get-PortOwnerSummary -Port $Port
        return [pscustomobject]@{ Started = $false; Outcome = "SKIP"; Detail = "Cổng $Port đang được dùng bởi $ownerSummary. $Module bind cổng cố định và không có port override; giữ SKIP, không dừng process và không đổi cổng bằng cách vá ứng dụng." }
    }

    $stdout = Join-Path $ArtifactRoot "$Name.stdout.log"
    $stderr = Join-Path $ArtifactRoot "$Name.stderr.log"
    try {
        $process = Start-Process -FilePath $script:VenvPython -ArgumentList "-X utf8 -m $Module" `
            -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    } catch {
        return [pscustomobject]@{ Started = $false; Outcome = "FAIL"; Detail = "Không khởi động được $Module`: $($_.Exception.Message)" }
    }

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) {
            $log = if (Test-Path $stderr) { (Get-Content $stderr -Raw -ErrorAction SilentlyContinue) } else { "" }
            return [pscustomobject]@{ Started = $false; Outcome = "FAIL"; Detail = "$Module thoát sớm (exit $($process.ExitCode)). $log" }
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $script:BackgroundApps += [pscustomobject]@{ Name = $Name; Pid = $process.Id; Url = $Url }
                return [pscustomobject]@{ Started = $true; Process = $process; Response = $response; Detail = "HTTP $($response.StatusCode), PID $($process.Id), $Url" }
            }
        } catch { }
    }
    if (-not $process.HasExited) {
        $script:BackgroundApps += [pscustomobject]@{ Name = $Name; Pid = $process.Id; Url = $Url }
    }
    return [pscustomobject]@{ Started = $false; Outcome = "FAIL"; Process = $process; Detail = "$Module không trả HTTP 200 trong 10 giây; xem log trong $ArtifactRoot." }
}

function Invoke-CachePerformanceMode {
    param([string]$Mode, [string]$FileStem)
    $csv = Join-Path $ArtifactRoot "$FileStem.csv"
    $markdown = Join-Path $ArtifactRoot "$FileStem.md"
    $arguments = @("--mode", $Mode, "--sizes", "1KB,100KB", "--runs", "2", "--rounds", "1",
                   "--csv", $csv, "--markdown", $markdown)
    $labCode = @'
import sys
import scripts.cache_performance as lab
mode = sys.argv[2]
lab.REDIS_PREFIX = "seminar:project-check:" + sys.argv[1] + ":performance:redis:"
lab.MEMCACHED_PREFIX = "seminar:project-check:" + sys.argv[1] + ":performance:memcached:"
try:
    lab.main(sys.argv[3:])
finally:
    if mode in ("all", "redis"):
        client = lab.RedisAdapter()
        for size in lab._parse_sizes("1KB,100KB"):
            client.delete(lab._cache_key(lab.REDIS_PREFIX, lab.make_payload(size), 1))
    if mode in ("all", "memcached"):
        client = lab.MemcachedAdapter()
        for size in lab._parse_sizes("1KB,100KB"):
            client.delete(lab._cache_key(lab.MEMCACHED_PREFIX, lab.make_payload(size), 1))
'@
    $labArguments = @($RunId, $Mode) + $arguments
    $labRun = Invoke-PythonSnippet -Code $labCode -Arguments $labArguments
    $output = $labRun.Output
    $exitCode = $labRun.ExitCode
    if ($exitCode -eq 0 -and (Test-Path $csv) -and (Test-Path $markdown)) {
        Write-Host ($output | Out-String).Trim()
        return [pscustomobject]@{ Succeeded = $true; Mode = $Mode; Csv = $csv; Markdown = $markdown; Detail = "" }
    }
    return [pscustomobject]@{ Succeeded = $false; Mode = $Mode; Csv = $csv; Markdown = $markdown; Detail = "exit $exitCode; $($output -join ' ')" }
}

foreach ($name in $script:CheckNames) {
    $script:Checks[$name] = [pscustomobject]@{ Name = $name; State = "SKIP"; Detail = "Chưa chạy." }
}

Write-Host "Redis Student Lookup Demo — kiểm tra an toàn" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Artifacts/test outputs (không ghi đè): $ArtifactRoot"

# Step 1: Verify this is the expected project and inspect Python/Docker.
$requiredPaths = @("README.md", "requirements.txt", "docker-compose.yml", "src\main.py",
                   "src\database.py", "src\cache.py", "src\cache_dashboard.py",
                   "src\session_demo.py", "src\sessions.py", "scripts\benchmark.py",
                   "scripts\cache_performance.py", "tests")
$missingPaths = @($requiredPaths | Where-Object { -not (Test-Path -LiteralPath (Join-Path $ProjectRoot $_)) })
if ($missingPaths.Count -eq 0) {
    Set-Check "Project Files" "PASS" "Đang ở project root; đủ README, Compose, source, scripts và tests."
} else {
    Set-Check "Project Files" "FAIL" ("Thiếu: " + ($missingPaths -join ", "))
}

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
$pythonVersion = $null
if ($pythonLauncher) {
    $versionText = (& py -3 --version 2>&1 | Out-String).Trim()
    if ($versionText -match "Python\s+(\d+\.\d+\.\d+)") {
        $pythonVersion = [version]$Matches[1]
    }
}
if ($pythonVersion -and $pythonVersion -ge [version]"3.10") {
    Set-Check "Python" "PASS" "Python $pythonVersion qua py -3."
} elseif ($pythonLauncher) {
    Set-Check "Python" "FAIL" "Không xác định được phiên bản Python 3.10+ từ py -3: $versionText"
} else {
    Set-Check "Python" "FAIL" "Không tìm thấy Python Launcher (py). Cần cài Python để tiếp tục."
}

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$DockerReady = $false
if (-not $dockerCommand) {
    Set-Check "Docker" "FAIL" "Không tìm thấy Docker CLI."
} else {
    $dockerVersion = (& docker --version 2>&1 | Out-String).Trim()
    $composeConfig = & docker compose config --quiet 2>&1
    $composeConfigExit = $LASTEXITCODE
    $dockerInfo = & docker info --format '{{.ServerVersion}}' 2>&1
    $dockerInfoExit = $LASTEXITCODE
    if ($dockerInfoExit -eq 0 -and $composeConfigExit -eq 0) {
        $DockerReady = $true
        Set-Check "Docker" "PASS" "$dockerVersion; Engine $($dockerInfo.Trim()); Compose config hợp lệ."
    } else {
        $detail = "CLI có sẵn ($dockerVersion), nhưng Engine/Compose chưa sẵn sàng. Mở Docker Desktop rồi chạy lại."
        if ($composeConfigExit -ne 0) { $detail += " Compose config lỗi: $($composeConfig -join ' ')" }
        if ($dockerInfoExit -ne 0) { $detail += " Engine: $($dockerInfo -join ' ')" }
        Set-Check "Docker" "FAIL" $detail
    }
}

# Step 2: Create the project venv if needed, then install only declared requirements when imports are missing.
$venvDir = Join-Path $ProjectRoot ".venv"
$script:VenvPython = Join-Path $venvDir "Scripts\python.exe"
if ($pythonVersion -and $pythonVersion -ge [version]"3.10" -and -not (Test-Path -LiteralPath $script:VenvPython)) {
    Write-Host "Tạo .venv..."
    & py -3 -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Host "Tạo .venv thất bại (exit $LASTEXITCODE)." -ForegroundColor Red }
}

$DependenciesReady = $false
if ($pythonVersion -and $pythonVersion -ge [version]"3.10" -and (Test-Path -LiteralPath $script:VenvPython)) {
    $dependencyCheckCode = 'import redis, pymemcache, pytest; print(''redis, pymemcache, pytest: import OK'')'
    $dependencyRun = Invoke-PythonSnippet -Code $dependencyCheckCode
    $dependencyCheck = $dependencyRun.Output
    $dependencyExit = $dependencyRun.ExitCode
    if ($dependencyExit -ne 0) {
        Write-Host "Thiếu dependency; cài đúng các package trong requirements.txt..."
        & $script:VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
        if ($LASTEXITCODE -eq 0) {
            $dependencyRun = Invoke-PythonSnippet -Code $dependencyCheckCode
            $dependencyCheck = $dependencyRun.Output
            $dependencyExit = $dependencyRun.ExitCode
        }
    }
    if ($dependencyExit -eq 0) {
        $DependenciesReady = $true
        Set-Check "Dependencies" "PASS" (($dependencyCheck | Out-String).Trim())
    } else {
        Set-Check "Dependencies" "FAIL" "Không cài/import được requirements.txt: $(($dependencyCheck | Out-String).Trim())"
    }
} else {
    Set-Check "Dependencies" "FAIL" "Không tạo/không tìm thấy .venv\Scripts\python.exe."
}

# Step 3: Start exactly the Compose services declared by this project and verify Redis two ways.
$RedisReady = $false
$MemcachedReady = $false
if ($DockerReady) {
    $composeUp = & docker compose up -d redis memcached 2>&1
    if ($LASTEXITCODE -eq 0) {
        $composeStatus = & docker compose ps 2>&1
        Write-Host ($composeStatus | Out-String).Trim()
        $runningServices = @(& docker compose ps --services --status running 2>$null)
        $redisPong = & docker compose exec -T redis redis-cli ping 2>&1
        $redisPongExit = $LASTEXITCODE
        $redisContainerOk = $runningServices -contains "redis"
        $RedisReady = $redisContainerOk -and $redisPongExit -eq 0 -and (($redisPong | Out-String).Trim() -eq "PONG")
        if ($RedisReady) {
            Set-Check "Redis" "PASS" "Compose service redis is running; redis-cli ping returned PONG."
        } else {
            Set-Check "Redis" "FAIL" "Container/PONG check failed. $($redisPong -join ' ')"
        }
        $MemcachedReady = $false
        if ($runningServices -contains "memcached") {
            for ($healthAttempt = 0; $healthAttempt -lt 30; $healthAttempt++) {
                $memcachedHealth = & docker inspect --format '{{.State.Health.Status}}' redis-student-demo-memcached 2>&1
                if ($LASTEXITCODE -eq 0 -and (($memcachedHealth | Out-String).Trim() -eq "healthy")) {
                    $MemcachedReady = $true
                    break
                }
                Start-Sleep -Seconds 1
            }
        }
        if ($MemcachedReady) {
            Set-Check "Memcached" "PASS" "Container redis-student-demo-memcached đang running và healthcheck báo healthy."
        } else {
            Set-Check "Memcached" "FAIL" "Memcached không ở trạng thái healthy. $($memcachedHealth -join ' ')"
        }
        if ($RedisReady -and $DependenciesReady) {
            $pythonPingCode = 'from src.cache import create_redis_client; c=create_redis_client(); c.ping(); print(''Python Redis PING OK'')'
            $pythonPingRun = Invoke-PythonSnippet -Code $pythonPingCode
            if ($pythonPingRun.ExitCode -eq 0) {
                Set-Check "Redis Python Client" "PASS" (($pythonPingRun.Output | Out-String).Trim())
            } else {
                Set-Check "Redis Python Client" "FAIL" (($pythonPingRun.Output | Out-String).Trim())
            }
        } else {
            Set-Check "Redis Python Client" "SKIP" "Cần Redis và dependencies sẵn sàng."
        }
    } else {
        Set-Check "Redis" "FAIL" "docker compose up thất bại: $($composeUp -join ' ')"
        Set-Check "Memcached" "FAIL" "docker compose up thất bại: $($composeUp -join ' ')"
    }
} else {
    Set-Check "Redis" "SKIP" "Docker Engine chưa sẵn sàng; không thể start/kiểm tra container."
    Set-Check "Memcached" "SKIP" "Docker Engine chưa sẵn sàng; không thể start/kiểm tra container."
    Set-Check "Redis Python Client" "SKIP" "Redis chưa sẵn sàng."
}

# Step 4: Read-only check of the configured SQLite database. Never initialize or write it.
if ($DependenciesReady) {
    $dbCheck = @'
import json, sqlite3, sys
from src.database import DB_PATH
path = DB_PATH.expanduser().resolve()
if not path.is_file():
    print(json.dumps({"state":"missing","path":str(path)}))
    raise SystemExit(0)
try:
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "students" not in tables:
        print(json.dumps({"state":"missing_table","path":str(path)}))
    else:
        count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        print(json.dumps({"state":"ok","path":str(path),"student_rows":count}))
    conn.close()
except Exception as exc:
    print(json.dumps({"state":"error","path":str(path),"error":str(exc)}))
    raise SystemExit(2)
'@
    $dbRun = Invoke-PythonSnippet -Code $dbCheck
    $dbOutput = $dbRun.Output
    if ($dbRun.ExitCode -eq 0) {
        try { $dbInfo = (($dbOutput | Select-Object -Last 1) | ConvertFrom-Json) } catch { $dbInfo = $null }
        if ($dbInfo -and $dbInfo.state -eq "ok") {
            Set-Check "Database" "PASS" "SQLite read-only query succeeded; table students has $($dbInfo.student_rows) row(s). Path: $($dbInfo.path)"
        } elseif ($dbInfo -and $dbInfo.state -eq "missing") {
            Set-Check "Database" "SKIP" "Database chưa tồn tại; script không tự tạo/seed để tránh thay đổi dữ liệu. Expected path: $($dbInfo.path)"
        } elseif ($dbInfo -and $dbInfo.state -eq "missing_table") {
            Set-Check "Database" "FAIL" "Database có nhưng chưa có bảng students: $($dbInfo.path). Dùng CLI có chủ đích để khởi tạo sau khi sao lưu/đồng ý."
        } else {
            Set-Check "Database" "FAIL" "Không xác nhận được database ở chế độ read-only: $($dbOutput -join ' ')"
        }
    } else {
        Set-Check "Database" "FAIL" "SQLite read-only check lỗi: $($dbOutput -join ' ')"
    }
} else {
    Set-Check "Database" "SKIP" "Python dependencies chưa sẵn sàng."
}

# Step 5: Compile source and tests, then run the repository's actual pytest suite.
$pythonFiles = @()
foreach ($folder in @("src", "scripts", "tests")) {
    $pythonFiles += @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot $folder) -Filter "*.py" -File -Recurse -ErrorAction SilentlyContinue)
}
if ($DependenciesReady) {
    & $script:VenvPython -m compileall -q src scripts tests
    if ($LASTEXITCODE -eq 0) {
        Set-Check "Python Compile" "PASS" "$($pythonFiles.Count) Python file(s) compiled."
    } else {
        Set-Check "Python Compile" "FAIL" "compileall exit code $LASTEXITCODE."
    }
    $testOutput = & $script:VenvPython -m pytest -q 2>&1
    $testExit = $LASTEXITCODE
    $testText = $testOutput | Out-String
    Write-Host $testText.Trim()
    $testDetail = "pytest exit $testExit; không phân tích được summary, xem output phía trên."
    if ($testText -match "(?m)(?:(\d+) failed,\s*)?(?:(\d+) passed)(?:,\s*(\d+) skipped)?") {
        $failedTests = if ($Matches[1]) { [int]$Matches[1] } else { 0 }
        $passedTests = [int]$Matches[2]
        $skippedTests = if ($Matches[3]) { [int]$Matches[3] } else { 0 }
        $testDetail = "passed=$passedTests, failed=$failedTests, skipped=$skippedTests"
    }
    if ($testExit -eq 0) {
        Set-Check "Unit Tests" "PASS" $testDetail
    } else {
        Set-Check "Unit Tests" "FAIL" $testDetail
    }
} else {
    Set-Check "Python Compile" "SKIP" "Python venv/dependencies chưa sẵn sàng."
    Set-Check "Unit Tests" "SKIP" "Python venv/dependencies chưa sẵn sàng."
}

# Step 6: Exercise cache-aside with an in-memory source record and a unique Redis key.
if ($RedisReady -and $DependenciesReady) {
    $cacheCheck = @'
import json, secrets
from src.cache import StudentService, create_redis_client
class TestDatabase:
    def __init__(self, row): self.row = row
    def get_student(self, student_id): return self.row if student_id == self.row["student_id"] else None
client = create_redis_client()
token = secrets.token_hex(10)
student_id = "AUTO_" + token
prefix = "seminar:project-check:" + token + ":"
row = {"student_id": student_id, "name": "Automated Check", "email": "check@example.invalid", "major": "Test"}
service = StudentService(TestDatabase(row), client, ttl=60, key_prefix=prefix)
key = prefix + student_id
try:
    first, miss = service.get_student(student_id)
    second, hit = service.get_student(student_id)
    ttl = client.ttl(key)
    ok = miss == "MISS" and hit == "HIT" and first == row and second == row and ttl > 0
    print(json.dumps({"ok":ok,"miss":miss,"hit":hit,"ttl":ttl,"same_record":first == second}))
    raise SystemExit(0 if ok else 3)
finally:
    client.delete(key)
'@
    $cacheRun = Invoke-PythonSnippet -Code $cacheCheck
    $cacheOutput = $cacheRun.Output
    if ($cacheRun.ExitCode -eq 0) {
        $cacheInfo = (($cacheOutput | Select-Object -Last 1) | ConvertFrom-Json)
        Set-Check "Cache-Aside" "PASS" "MISS → HIT; cùng record; TTL $($cacheInfo.ttl)s. Chỉ key test ngẫu nhiên đã bị xóa."
    } else {
        Set-Check "Cache-Aside" "FAIL" "Cache-aside integration thất bại: $($cacheOutput -join ' ')"
    }
} else {
    Set-Check "Cache-Aside" "SKIP" "Cần Redis PONG và dependencies."
}

# Step 7: Start the real Session Demo only on a free port, then exercise existing HTTP routes.
$SessionUrl = "http://127.0.0.1:5000"
$SessionStarted = $false
if (-not $RedisReady) {
    Set-Check "Session Storage" "SKIP" "Redis chưa PONG; Session Demo yêu cầu kết nối Redis khi khởi động."
} elseif ($DependenciesReady) {
    $sessionApp = Start-ProjectWebApp -Name "session-demo" -Module "src.session_demo" -Port 5000 -Url $SessionUrl
    $SessionStarted = $sessionApp.Started
    if ($SessionStarted) {
        $sessionOverrides = [bool]$env:SESSION_DEMO_USERNAME -or [bool]$env:SESSION_PASSWORD_HASH
        if (-not $RedisReady) {
            Set-Check "Session Storage" "SKIP" "UI đã chạy tại $SessionUrl; test session cần Redis. PID $($sessionApp.Process.Id)."
        } elseif ($sessionOverrides) {
            Set-Check "Session Storage" "SKIP" "UI đã chạy; auth env override đang được đặt nên script không thay đổi credential. Bỏ override có chủ đích để test credential mặc định."
        } else {
            $sessionCheck = @'
import json, re, sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener
from src.cache import create_redis_client
from src.sessions import SessionStore
base = sys.argv[1]
cookie_jar = CookieJar()
opener = build_opener(HTTPCookieProcessor(cookie_jar))
client = create_redis_client()
sid = None
key = None
result = {"ok":False,"login_status":None,"status_endpoint":None,"protected_status":None,"logout_status":None,"expired_protected_status":None,"ttl":None,"redis_record":False,"key_removed":False}
def request(path, data=None):
    req = Request(base + path, data=urlencode(data).encode() if data is not None else None)
    try:
        with opener.open(req, timeout=5) as response: return response.status, response.read().decode("utf-8")
    except HTTPError as exc: return exc.code, exc.read().decode("utf-8")
try:
    code, page = request("/")
    match = re.search(r"name='csrf' value='([^']+)'", page)
    if code != 200 or not match: raise RuntimeError("GET / did not provide the existing CSRF form")
    csrf = match.group(1)
    result["login_status"], _ = request("/login", {"csrf":csrf,"username":"demo","password":"redis123"})
    sid = next((cookie.value for cookie in cookie_jar if cookie.name == "seminar_session"), None)
    if not sid: raise RuntimeError("Login response did not set session cookie")
    key = SessionStore.key(sid)
    result["status_endpoint"], status_page = request("/status")
    result["ttl"] = client.ttl(key)
    record = client.get(key)
    session_data = json.loads(record) if record else None
    result["redis_record"] = session_data == {"username":"demo"}
    result["protected_status"], _ = request("/protected", {"csrf":csrf})
    result["logout_status"], _ = request("/logout", {"csrf":csrf})
    result["key_removed"] = client.ttl(key) == -2
    result["expired_protected_status"], _ = request("/protected", {"csrf":csrf})
    result["ok"] = (result["login_status"] == 200 and result["status_endpoint"] == 200 and
        "Đang đăng nhập:" in status_page and result["ttl"] > 0 and result["redis_record"] and
        result["protected_status"] == 200 and result["logout_status"] == 200 and
        result["key_removed"] and result["expired_protected_status"] == 401)
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 4)
finally:
    if key: client.delete(key)
'@
            $sessionRun = Invoke-PythonSnippet -Code $sessionCheck -Arguments @($SessionUrl)
            $sessionOutput = $sessionRun.Output
            if ($sessionRun.ExitCode -eq 0) {
                $sessionInfo = (($sessionOutput | Select-Object -Last 1) | ConvertFrom-Json)
                Set-Check "Session Storage" "PASS" "Create/check/protected/logout verified; TTL $($sessionInfo.ttl)s; exact session key removed. Session ID not printed. PID $($sessionApp.Process.Id)."
            } else {
                Set-Check "Session Storage" "FAIL" "HTTP/session integration thất bại: $($sessionOutput -join ' '); PID $($sessionApp.Process.Id)."
            }
        }
    } else {
        Set-Check "Session Storage" $sessionApp.Outcome $sessionApp.Detail
    }
} else {
    Set-Check "Session Storage" "SKIP" "Dependencies chưa sẵn sàng; không khởi động app."
}

# Step 8: Dashboard routes confirmed in src/cache_dashboard.py: GET / and GET /api/status.
$DashboardUrl = "http://127.0.0.1:5001"
if (-not $RedisReady) {
    Set-Check "Dashboard" "SKIP" "Redis chưa sẵn sàng; Dashboard status endpoint cần ping Redis."
} elseif ($DependenciesReady) {
    $dashboardApp = Start-ProjectWebApp -Name "cache-dashboard" -Module "src.cache_dashboard" -Port 5001 -Url $DashboardUrl
    if ($dashboardApp.Started) {
        try {
            $statusResponse = Invoke-WebRequest -Uri "$DashboardUrl/api/status" -UseBasicParsing -TimeoutSec 3
            $statusInfo = $statusResponse.Content | ConvertFrom-Json
            if ($dashboardApp.Response.StatusCode -eq 200 -and $statusResponse.StatusCode -eq 200 -and $statusInfo.connected) {
                Set-Check "Dashboard" "PASS" "GET / và GET /api/status trả HTTP 200, Redis connected=true. URL $DashboardUrl; PID $($dashboardApp.Process.Id)."
            } else {
                Set-Check "Dashboard" "FAIL" "GET / trả HTTP $($dashboardApp.Response.StatusCode); /api/status HTTP $($statusResponse.StatusCode), connected=$($statusInfo.connected). PID $($dashboardApp.Process.Id)."
            }
        } catch {
            Set-Check "Dashboard" "FAIL" "Dashboard UI chạy ở $DashboardUrl nhưng /api/status lỗi: $($_.Exception.Message)"
        }
    } else {
        Set-Check "Dashboard" $dashboardApp.Outcome $dashboardApp.Detail
    }
} else {
    Set-Check "Dashboard" "SKIP" "Dependencies chưa sẵn sàng."
}

# Step 9: Benchmarks use unique temp output. The SQLite benchmark runs from a copy to isolate its fixed DB path.
if (-not $DependenciesReady) {
    Set-Check "Benchmark" "SKIP" "Dependencies chưa sẵn sàng."
} else {
    $benchmarkFailures = @()
    $benchmarkSuccesses = @()
    if ($RedisReady -and $MemcachedReady) {
        $labResult = Invoke-CachePerformanceMode -Mode "all" -FileStem "cache-performance"
        if ($labResult.Succeeded) { $benchmarkSuccesses += "NO CACHE/Redis/Memcached" }
        else { $benchmarkFailures += "Cache Performance Lab: $($labResult.Detail)" }
    } else {
        $noCacheResult = Invoke-CachePerformanceMode -Mode "no-cache" -FileStem "cache-performance-no-cache"
        if ($noCacheResult.Succeeded) { $benchmarkSuccesses += "NO CACHE" }
        else { $benchmarkFailures += "NO CACHE: $($noCacheResult.Detail)" }
        if ($RedisReady) {
            $redisResult = Invoke-CachePerformanceMode -Mode "redis" -FileStem "cache-performance-redis"
            if ($redisResult.Succeeded) { $benchmarkSuccesses += "Redis" }
            else { $benchmarkFailures += "Redis mode: $($redisResult.Detail)" }
        }
        if ($MemcachedReady) {
            $memcachedResult = Invoke-CachePerformanceMode -Mode "memcached" -FileStem "cache-performance-memcached"
            if ($memcachedResult.Succeeded) { $benchmarkSuccesses += "Memcached" }
            else { $benchmarkFailures += "Memcached mode: $($memcachedResult.Detail)" }
        }
    }

    if ($RedisReady) {
        $isolatedRoot = Join-Path $ArtifactRoot "sqlite-redis-benchmark-project"
        New-Item -ItemType Directory -Path (Join-Path $isolatedRoot "scripts"), (Join-Path $isolatedRoot "src"), (Join-Path $isolatedRoot "data") -Force | Out-Null
        $benchmarkCopy = Join-Path $isolatedRoot "scripts\benchmark.py"
        Copy-Item -LiteralPath (Join-Path $ProjectRoot "scripts\benchmark.py") -Destination $benchmarkCopy
        Copy-Item -LiteralPath (Join-Path $ProjectRoot "scripts\__init__.py") -Destination (Join-Path $isolatedRoot "scripts\__init__.py")
        Copy-Item -LiteralPath (Join-Path $ProjectRoot "src\cache.py") -Destination (Join-Path $isolatedRoot "src\cache.py")
        Copy-Item -LiteralPath (Join-Path $ProjectRoot "src\__init__.py") -Destination (Join-Path $isolatedRoot "src\__init__.py")
        $benchmarkPrefix = "seminar:project-check:benchmark:$($RunId):"
        $benchmarkSource = [System.IO.File]::ReadAllText($benchmarkCopy)
        $oldPrefixLine = 'PREFIX = "seminar:benchmark:student:"'
        if (-not $benchmarkSource.Contains($oldPrefixLine)) {
            $benchmarkFailures += "SQLite/Redis: không tìm thấy prefix source mong đợi; benchmark không chạy vì không thể giới hạn key an toàn."
        } else {
            $isolatedPrefixLine = 'PREFIX = "' + $benchmarkPrefix + '"'
            [System.IO.File]::WriteAllText($benchmarkCopy, $benchmarkSource.Replace($oldPrefixLine, $isolatedPrefixLine), [System.Text.UTF8Encoding]::new($false))
        }
        $sqliteCsv = Join-Path $ArtifactRoot "sqlite-redis.csv"
        $sqliteMd = Join-Path $ArtifactRoot "sqlite-redis.md"
        if ($benchmarkSource.Contains($oldPrefixLine)) {
            $sqliteExit = 1
            $cleanupExit = 0
            Push-Location $isolatedRoot
            try {
                $sqliteOutput = & $script:VenvPython -X utf8 -m scripts.benchmark --dataset-size 5 --queries 5 --repetitions 1 --csv $sqliteCsv --markdown $sqliteMd 2>&1
                $sqliteExit = $LASTEXITCODE
            } finally {
                $cleanupCode = @'
import json, sys
from src.cache import create_redis_client
client = create_redis_client()
prefix = sys.argv[1]
keys = list(client.scan_iter(match=prefix + "*"))
deleted = client.delete(*keys) if keys else 0
print(json.dumps({"found":len(keys),"deleted":deleted}))
'@
                $cleanupRun = Invoke-PythonSnippet -Code $cleanupCode -Arguments @($benchmarkPrefix)
                $cleanupOutput = $cleanupRun.Output
                $cleanupExit = $cleanupRun.ExitCode
                Pop-Location
            }
            if ($sqliteExit -eq 0 -and $cleanupExit -eq 0 -and (Test-Path $sqliteCsv) -and (Test-Path $sqliteMd)) {
                Write-Host ($sqliteOutput | Out-String).Trim()
                $benchmarkSuccesses += "SQLite/Redis"
            } else {
                $benchmarkFailures += "SQLite/Redis: benchmark exit $sqliteExit; isolated cache-key cleanup exit $cleanupExit; $($sqliteOutput -join ' ') $($cleanupOutput -join ' ')"
            }
        }
    }

    if ($benchmarkFailures.Count -gt 0) {
        Set-Check "Benchmark" "FAIL" ($benchmarkFailures -join " | ")
    } elseif ($RedisReady -and $MemcachedReady) {
        Set-Check "Benchmark" "PASS" "Cache Performance Lab compared all modes; SQLite/Redis ran in an isolated temporary project. Outputs/DB are under $ArtifactRoot."
    } else {
        $unavailable = @()
        if (-not $RedisReady) { $unavailable += "Redis" }
        if (-not $MemcachedReady) { $unavailable += "Memcached" }
        Set-Check "Benchmark" "SKIP" "Ran $($benchmarkSuccesses -join ', '); unavailable modes skipped: $($unavailable -join ', '). Outputs are under $ArtifactRoot."
    }
}

# Step 10: Report results, app URLs, background PIDs, and safe manual cleanup.
Write-Host ""
Write-Host "=== TỔNG KẾT ===" -ForegroundColor Cyan
Write-Host ("{0,-22} {1,-8} {2}" -f "Hạng mục", "Trạng thái", "Chi tiết")
Write-Host ("{0,-22} {1,-8} {2}" -f ("-" * 20), ("-" * 8), ("-" * 50))
foreach ($name in $script:CheckNames) {
    $item = $script:Checks[$name]
    Write-Host ("{0,-22} {1,-8} {2}" -f $name, $item.State, $item.Detail)
}
$passed = @($script:Checks.Values | Where-Object State -eq "PASS").Count
$failed = @($script:Checks.Values | Where-Object State -eq "FAIL").Count
$skipped = @($script:Checks.Values | Where-Object State -eq "SKIP").Count
Write-Host ""
Write-Host "PASS: $passed | FAIL: $failed | SKIP: $skipped"
Write-Host "Tổng output/log/test (không ghi đè): $ArtifactRoot"
Write-Host "URLs để demo:"
Write-Host "  Session Demo: $SessionUrl"
Write-Host "  Cache Dashboard: $DashboardUrl"
Write-Host "Các app do script khởi động vẫn chạy nền để mở demo:"
if ($script:BackgroundApps.Count -gt 0) {
    foreach ($app in $script:BackgroundApps) { Write-Host ("  {0}: PID {1}, {2}" -f $app.Name, $app.Pid, $app.Url) }
    Write-Host "Sau khi demo, dùng Stop-Process -Id với PID tương ứng được in phía trên."
} else {
    Write-Host "  Không có app nào được khởi động."
}
if ($script:Failures.Count -gt 0) {
    Write-Host "Các lỗi cần khắc phục:"
    foreach ($failure in $script:Failures) { Write-Host "  - $failure" -ForegroundColor Red }
} else {
    Write-Host "Các lỗi cần khắc phục: không có FAIL. Xem SKIP để biết bước chưa chạy."
}
Write-Host "Thao tác thủ công: Docker Desktop phải đang mở; sau khi demo, dừng app PID ở trên và chạy docker compose down nếu muốn dừng services."
if ($failed -gt 0) { exit 1 } else { exit 0 }
