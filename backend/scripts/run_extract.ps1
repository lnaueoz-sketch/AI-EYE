$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$log = Join-Path $root "python_check.log"
"" | Out-File $log -Encoding utf8
$cands = New-Object System.Collections.Generic.List[string]
foreach ($p in @("$root\venv\Scripts\python.exe")) { $cands.Add($p) }
foreach ($name in @("python","python3","py")) {
  Get-Command $name -All -ErrorAction SilentlyContinue | ForEach-Object { $cands.Add($_.Source) }
}
$globs = @("$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
  "$env:USERPROFILE\anaconda3\python.exe", "$env:USERPROFILE\anaconda3\envs\*\python.exe",
  "$env:USERPROFILE\miniconda3\python.exe", "$env:USERPROFILE\miniconda3\envs\*\python.exe",
  "$env:USERPROFILE\.conda\envs\*\python.exe", "$env:ProgramData\anaconda3\python.exe",
  "$env:ProgramData\anaconda3\envs\*\python.exe", "C:\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe")
foreach ($g in $globs) { Get-ChildItem $g -ErrorAction SilentlyContinue | ForEach-Object { $cands.Add($_.FullName) } }
$envtxt = "$env:USERPROFILE\.conda\environments.txt"
if (Test-Path $envtxt) { Get-Content $envtxt | ForEach-Object { $cands.Add((Join-Path $_.Trim() "python.exe")) } }
$found = $null
foreach ($py in ($cands | Select-Object -Unique)) {
  if (-not (Test-Path $py) -and $py -notmatch '^(python|py)') { continue }
  $code = "import sys`nok=1`nfor m in ('ultralytics','cv2','torch','numpy'):`n  try:`n    __import__(m); print(m,'OK')`n  except Exception as e:`n    ok=0; print(m,'FAIL',type(e).__name__,e)`nprint('python',sys.version.split()[0]); sys.exit(0 if ok else 1)"
  $pa = @("-c",$code)
  if ($py -like "*\py.exe") { $pa = @("-3") + $pa }
  $out = & $py @pa 2>&1 | Out-String
  ("[{0}] exit={1}`n{2}" -f $py, $LASTEXITCODE, $out.Trim()) | Out-File $log -Append -Encoding utf8
  if ($LASTEXITCODE -eq 0 -and -not $found) { $found = $py }
}
if (-not $found) {
  Write-Host "[ERROR] ultralytics 가 설치된 파이썬을 못 찾았어요. python_check.log 를 Claude 에게 알려주세요." -ForegroundColor Red
  exit 1
}
Write-Host "사용할 파이썬: $found" -ForegroundColor Green
$pyArgs = @()
if ($found -like "*\py.exe") { $pyArgs = @("-3") }
& $found @pyArgs "scripts\extract_keypoints.py" "--dataset" "datasets\aihub_dump"
