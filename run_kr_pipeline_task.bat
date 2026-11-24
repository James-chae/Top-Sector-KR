@echo off
chcp 65001 > nul
setlocal EnableExtensions

REM 실행 중 git reset --hard가 이 파일을 덮어써도 cmd가 엉뚱한 줄을 읽지 않도록
REM 임시 복사본으로 실행한다. 작업 폴더는 아래 cd /d 절대경로로 고정된다.
if /i not "%~1"=="--inner" (
  copy /y "%~f0" "%TEMP%\kr_pipeline_task_run.bat" >nul || exit /b 1
  call "%TEMP%\kr_pipeline_task_run.bat" --inner
  exit /b
)

cd /d "C:\Users\solom\OneDrive\바탕 화면\Top Sector\Top-Sector-KR"

REM ============================================================
REM  2026-09-16 장애 대응: git 네트워크 명령이 응답 없이 멈춰버리면
REM  Task Scheduler가 "이전 실행 중" 상태로 인식해 몇 시간씩 다음
REM  실행을 아예 건너뛰는 문제가 있었음.
REM  -> git의 저속/무응답 전송을 자동으로 중단시키는 환경변수 추가.
REM     (20초간 전송속도가 1000바이트/초 미만이면 강제 중단)
REM ============================================================
set GIT_HTTP_LOW_SPEED_LIMIT=1000
set GIT_HTTP_LOW_SPEED_TIME=20

echo ==================================================>>task_run_log.txt
echo [%date% %time%] START>>task_run_log.txt

REM ============================================================
REM  2026-11 장애 대응: pull --rebase 충돌로 push 실패 커밋이
REM  1,707개 쌓였음.
REM  -> rebase를 쓰지 않는다. 시작할 때 origin/main과 똑같이 맞추고,
REM     history 파일은 파이프라인이 원격 최신본을 읽어 이어 쓴다.
REM ============================================================
echo [GIT] sync to origin/main>>task_run_log.txt
git rebase --abort >nul 2>&1
git fetch origin main >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail
git checkout -f main >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail
git reset --hard origin/main >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail

echo [PIPELINE] run_kr_pipeline.py>>task_run_log.txt
"C:\Program Files\Python312\python.exe" "C:\Users\solom\OneDrive\바탕 화면\Top Sector\Top-Sector-KR\scripts\run_kr_pipeline.py" >>task_run_log.txt 2>&1
if errorlevel 1 goto :fail

echo [GIT] status before add>>task_run_log.txt
git status --short >>task_run_log.txt 2>&1

echo [GIT] add data/config files>>task_run_log.txt
git add data\*.json config\scoring_config.json >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail

git diff --cached --quiet
if %errorlevel%==0 goto :nochanges

echo [GIT] commit>>task_run_log.txt
git commit -m "chore: auto update KR dashboard data" >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail

set RETRIED=0
:push
REM 안전장치: 로컬 커밋이 2개 이상이면 push하지 않고 버린다.
set AHEAD=0
for /f %%i in ('git rev-list --count origin/main..HEAD 2^>nul') do set AHEAD=%%i
if %AHEAD% GEQ 2 goto :dropcommits

echo [GIT] push origin main>>task_run_log.txt
git push origin main >>task_run_log.txt 2>&1
if not errorlevel 1 goto :success
if "%RETRIED%"=="1" goto :dropcommits

REM push 거부(원격에 새 커밋) -> 원격에 다시 맞추고 1회만 재생성 후 재시도
set RETRIED=1
echo [GIT] push rejected - resync and regenerate once>>task_run_log.txt
git fetch origin main >>task_run_log.txt 2>&1
if errorlevel 1 goto :dropcommits
git reset --hard origin/main >>task_run_log.txt 2>&1
if errorlevel 1 goto :dropcommits
"C:\Program Files\Python312\python.exe" "C:\Users\solom\OneDrive\바탕 화면\Top Sector\Top-Sector-KR\scripts\run_kr_pipeline.py" >>task_run_log.txt 2>&1
if errorlevel 1 goto :dropcommits
git add data\*.json config\scoring_config.json >>task_run_log.txt 2>&1
if errorlevel 1 goto :dropcommits
git diff --cached --quiet
if %errorlevel%==0 goto :nochanges
git commit -m "chore: auto update KR dashboard data" >>task_run_log.txt 2>&1
if errorlevel 1 goto :dropcommits
goto :push

:success
echo [%date% %time%] END - SUCCESS>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 0

:dropcommits
echo [GIT][ERROR] push failed - discard local commit>>task_run_log.txt
git reset --hard origin/main >>task_run_log.txt 2>&1
goto :gitfail

:nochanges
echo [GIT] no data changes to commit>>task_run_log.txt
echo [%date% %time%] END - NO CHANGES>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 0

:gitfail
echo [GIT][ERROR] auto push failed>>task_run_log.txt
git status --short >>task_run_log.txt 2>&1
echo [%date% %time%] END - GIT FAIL>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 1

:fail
echo [PIPELINE][ERROR] run_kr_pipeline.py failed>>task_run_log.txt
echo [%date% %time%] END - PIPELINE FAIL>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 1
