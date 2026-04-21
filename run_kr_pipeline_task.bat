@echo off
chcp 65001 > nul
setlocal EnableExtensions

cd /d "C:\Users\solom\OneDrive\바탕 화면\Top Sector\Top-Sector-KR"

echo ==================================================>>task_run_log.txt
echo [%date% %time%] START>>task_run_log.txt

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

echo [GIT] pull --rebase origin main>>task_run_log.txt
git pull --rebase origin main >>task_run_log.txt 2>&1
if errorlevel 1 goto :rebasefix

goto :push

:rebasefix
echo [GIT] rebase conflict detected - try keep local generated json>>task_run_log.txt

git checkout --ours data\dashboard_meta.json >>task_run_log.txt 2>&1
git checkout --ours data\latest_krx.json >>task_run_log.txt 2>&1
git checkout --ours data\leader_board.json >>task_run_log.txt 2>&1
git checkout --ours data\market_raw.json >>task_run_log.txt 2>&1
git checkout --ours data\sector_calendar_history.json >>task_run_log.txt 2>&1

git add data\dashboard_meta.json data\latest_krx.json data\leader_board.json data\market_raw.json data\sector_calendar_history.json >>task_run_log.txt 2>&1
git rebase --continue >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail

:push
echo [GIT] push origin main>>task_run_log.txt
git push origin main >>task_run_log.txt 2>&1
if errorlevel 1 goto :gitfail

echo [%date% %time%] END - SUCCESS>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 0

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