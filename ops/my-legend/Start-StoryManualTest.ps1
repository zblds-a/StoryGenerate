param([string]$Python, [string]$KeyFile, [switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion -lt [Version]'7.4') { throw 'Use PowerShell 7.4 or newer (pwsh).' }
. "$PSScriptRoot/Startup.Common.ps1"
$manualRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$manualRuntime = Join-Path $manualRoot 'runtime/story-manual-test'
$manualEngine = Join-Path $manualRoot 'source/StoryGenerate-0dec8480e3c1b01af66407ff063f825a3fd5dedb'
$manualContainer = 'storygenerate-manual-test'
$manualState = Join-Path $manualRuntime 'processes.json'
if ($Stop) {
    if (Test-Path -LiteralPath $manualState) {
        foreach ($item in (Get-Content -LiteralPath $manualState -Raw | ConvertFrom-Json)) {
            $entry = Resolve-LegendPidFile $item.pid_file $item.executable $item.arguments
            if ($entry) { Stop-Process -Id $entry.ProcessId; Write-Output ($item.name + ' stopped') }
        }
    }
    $label = & docker inspect --format '{{index .Config.Labels "storygenerate.manual"}}' $manualContainer 2>$null
    if ($LASTEXITCODE -eq 0 -and $label -eq '1') { & docker stop $manualContainer }
    return
}
if (!$Python) { $Python = Join-Path $manualRoot '.venv-interactive/Scripts/python.exe' }
if (!(Test-Path -LiteralPath $Python)) { throw 'Python environment missing. Pass -Python with an installed project environment.' }
$manualNode = (Get-Command node -ErrorAction Stop).Source
$manualFrontend = Join-Path $manualRoot 'source/fingertip-legend-app'
$manualUni = Join-Path $manualFrontend 'node_modules/@dcloudio/vite-plugin-uni/bin/uni.js'
if (!(Test-Path -LiteralPath $manualUni)) { throw 'Run npm ci in source/fingertip-legend-app first.' }
$manualKey = $env:DRAMA_LLM_API_KEY
if ($KeyFile) {
    $secured = (Get-Content -LiteralPath $KeyFile -Raw).Trim() | ConvertTo-SecureString
    try { $manualKey = [Net.NetworkCredential]::new('', $secured).Password } finally { $secured.Dispose() }
}
if (!$manualKey) { throw 'Set DRAMA_LLM_API_KEY or pass -KeyFile with this Windows user DPAPI encrypted key.' }
New-Item -ItemType Directory -Path $manualRuntime -Force | Out-Null
$manualRecords = [Collections.Generic.List[object]]::new()
$manualEnv = @{
    PYTHONPATH=((Join-Path $manualEngine '4-引擎代码') + ';' + (Join-Path $manualRoot 'source/my-legend-production/src'))
    PYTHONUTF8='1'; MY_LEGEND_INTERACTIVE_STORIES='1'; MY_LEGEND_PRODUCTION_MODULES=''; MY_LEGEND_MANUAL_STORY_TEST='1'
    STORY_DATABASE_URL='postgresql+psycopg://postgres:story-manual-local-only@127.0.0.1:25440/postgres'
    STORY_DATABASE_SCHEMA='story_manual_engine'
    MY_LEGEND_PRODUCTION_DSN='postgresql://postgres:story-manual-local-only@127.0.0.1:25440/postgres'
    MY_LEGEND_PRODUCTION_SCHEMA='story_manual'; MY_LEGEND_PRODUCTION_RUNTIME=(Join-Path $manualRuntime 'production')
    MY_LEGEND_STORY_RUNTIME=(Join-Path $manualRuntime 'app'); MY_LEGEND_STORY_URL='http://127.0.0.1:8897'
    STORY_IMAGE_BASE_URL=''; STORY_IMAGE_API_KEY=''; STORY_IMAGE_MODEL=''; DRAMA_LLM_API_KEY=''
}
$tokenPath = Join-Path $manualRuntime 'service-token.dpapi'
if (!(Test-Path -LiteralPath $tokenPath)) {
    $token = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
    ConvertTo-SecureString $token -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath $tokenPath
}
$secured = (Get-Content -LiteralPath $tokenPath -Raw).Trim() | ConvertTo-SecureString
try { $token = [Net.NetworkCredential]::new('', $secured).Password } finally { $secured.Dispose() }
$manualEnv.MY_LEGEND_STORY_TOKEN = $token
$manualEnv.STORY_API_KEYS = (@{$token=@{principal_id='story-manual';admin=$true}} | ConvertTo-Json -Compress)
function Start-ManualService($Name, $Executable, $Arguments, $Directory, $Extra=@{}, [switch]$Wait) {
    $pidPath = Join-Path $manualRuntime ($Name + '.pid')
    if (!$Wait) {
        $manualRecords.Add(@{name=$Name;pid_file=$pidPath;executable=$Executable;arguments=$Arguments})
        $manualRecords | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manualState
        if (Resolve-LegendPidFile $pidPath $Executable $Arguments) { Write-Output "$Name reused"; return }
    }
    $childEnv = $manualEnv.Clone()
    foreach ($pair in $Extra.GetEnumerator()) { $childEnv[$pair.Key] = $pair.Value }
    $child = Start-LegendProcess -FilePath $Executable -Arguments $Arguments -WorkingDirectory $Directory -Environment $childEnv `
        -StandardOutput (Join-Path $manualRuntime ($Name+'.out.log')) -StandardError (Join-Path $manualRuntime ($Name+'.err.log')) -Wait:$Wait
    if ($Wait) { if ($child.ExitCode) { throw "$Name failed; see runtime/story-manual-test/$Name.err.log" } }
    else { Write-LegendPidFile $pidPath $child.Id; Write-Output "$Name started" }
}
try {
    foreach ($port in @(8897,8895,5193)) {
        $expected = switch ($port) {8897 {'drama_engine.service serve'} 8895 {'run_story_manual_api.py'} 5193 {$manualUni}}
        $executable = if ($port -eq 5193) {$manualNode} else {$Python}
        $listening = Assert-LegendListener $port $expected $executable
        $name = switch ($port) {8897 {'catalog-api'} 8895 {'business-api'} 5193 {'frontend'}}
        if ($listening -and !(Resolve-LegendPidFile (Join-Path $manualRuntime ($name+'.pid')) $executable $expected)) {
            throw "Port $port belongs to another environment. Stop that environment first; it will not be terminated here."
        }
    }
    $database = & docker ps -a --filter "name=^/$manualContainer`$" --format '{{.Names}}'
    if (!$database) {
        & docker create --name $manualContainer --label storygenerate.manual=1 -p '127.0.0.1:25440:5432' `
            -e POSTGRES_PASSWORD=story-manual-local-only postgres:16-alpine | Out-Null
        if ($LASTEXITCODE) { throw 'Docker database creation failed. Start Docker Desktop and retry.' }
    }
    $label = & docker inspect --format '{{index .Config.Labels "storygenerate.manual"}}' $manualContainer
    if ($label -ne '1') { throw 'Container name belongs to a different environment.' }
    & docker start $manualContainer | Out-Null
    $ready = $false
    for ($attempt=0;$attempt -lt 30;$attempt++) {
        & docker exec $manualContainer pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) {$ready=$true;break}; Start-Sleep -Milliseconds 500
    }
    if (!$ready) { throw 'Manual PostgreSQL database did not become ready.' }
    Start-ManualService 'engine-migrate' $Python '-m drama_engine.service migrate' $manualEngine @{} -Wait
    Start-ManualService 'session-migrate' $Python ('"'+(Join-Path $PSScriptRoot 'run_interactive_story_worker.py')+'" --migrate') $manualRoot @{} -Wait
    Start-ManualService 'catalog-api' $Python '-m drama_engine.service serve --host 127.0.0.1 --port 8897' $manualEngine
    Wait-LegendHttp 'http://127.0.0.1:8897/health' 'Character service'
    $headers = @{Authorization=('Bearer '+$token)}
    foreach ($role in @(@{id='legend-moyu';name='墨羽'},@{id='legend-lingmo';name='灵墨'})) {
        try { $null=Invoke-RestMethod ('http://127.0.0.1:8897/v1/characters/'+$role.id) -Headers $headers }
        catch {
            if ([int]$_.Exception.Response.StatusCode -ne 404) { throw }
            $body=@{characters=@(@{character_id=$role.id;expected_version=0;canon=@{name=$role.name};runtime_defaults=@{};assets=@{}})} | ConvertTo-Json -Depth 8
            $null=Invoke-RestMethod 'http://127.0.0.1:8897/v1/characters/import' -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $body
        }
    }
    Start-ManualService 'business-api' $Python ('"'+(Join-Path $PSScriptRoot 'run_story_manual_api.py')+'"') $manualRoot
    Wait-LegendHttp 'http://127.0.0.1:8895/health' 'Business API'
    $workerEnv=@{DRAMA_LLM_API_KEY=$manualKey;DRAMA_LLM_BASE_URL='http://yunshu.xzmoma.cn:3001/v1';STORY_LLM_FAST_MODEL='deepseek-v4.1-flash-1017';STORY_LLM_BALANCED_MODEL='deepseek-v4.1-flash-1017';STORY_LLM_STRONG_MODEL='qwen/deepseek-v4-pro';STORY_INTERACTIVE_THINKING='disabled';STORY_INTERACTIVE_STREAMING='1'}
    Start-ManualService 'story-worker' $Python ('"'+(Join-Path $PSScriptRoot 'run_interactive_story_worker.py')+'"') $manualRoot $workerEnv
    Start-ManualService 'frontend' $manualNode ('"'+$manualUni+'" --host 127.0.0.1 --port 5193') $manualFrontend @{VITE_USE_MOCK='false';VITE_LOCAL_BACKEND='true';VITE_API_BASE_URL='http://127.0.0.1:8895/api/v1'}
    Wait-LegendHttp 'http://127.0.0.1:5193' 'Story frontend'
    $login=Invoke-RestMethod 'http://127.0.0.1:8895/api/v1/auth/local' -Method Post -ContentType 'application/json' -Body '{}'
    $checkHeaders=@{Authorization=('Bearer '+$login.data.accessToken)}
    $options=Invoke-RestMethod 'http://127.0.0.1:8895/api/v1/story-options' -Headers $checkHeaders
    $roles=Invoke-RestMethod 'http://127.0.0.1:8895/api/v1/characters' -Headers $checkHeaders
    if (!$options.data.enabled -or !$options.data.story_only -or @($roles.data).Count -ne 2) {
        throw 'Story-only readiness or manual character catalog check failed.'
    }
    $url='http://127.0.0.1:5193/#/pages/story-session/index'
    Write-Output "Ready: $url"
    Write-Output 'Use local login: 开始创作. Only story generation is enabled; backgrounds are disabled.'
    Write-Output "Logs: $manualRuntime"
    if (!$NoBrowser) { Start-Process $url | Out-Null }
} finally {
    $manualKey=$null; $manualEnv.Clear()
    if ($workerEnv) {$workerEnv.Clear()}
}
