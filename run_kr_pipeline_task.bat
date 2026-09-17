@echo off
chcp 65001 > nul
setlocal EnableExtensions

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

REM ============================================================
REM  2026-09-15~17 장애 대응: scripts\fetch_latest_krx.py 등
REM  data/config 외의 파일이 (줄바꿈 CRLF/LF 변환 등으로) 계속
REM  "수정됨" 상태로 남아있으면, git pull --rebase가
REM  "You have unstaged changes" 에러로 매번 거부되어 자동화가
REM  통째로 계속 실패하는 문제가 있었음.
REM  -> pull 직전에 관련 없는 수정사항을 잠깐 치워두고(stash),
REM     pull이 끝나면 다시 복원한다.
REM ============================================================
echo [GIT] stash unrelated tracked changes before pull>>task_run_log.txt
git stash push --quiet -m "auto-stash-before-pull" >>task_run_log.txt 2>&1

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
if errorlevel 1 goto :rebaseabort

goto :push

:rebaseabort
REM rebase --continue까지 실패하면 rebase 상태로 계속 남아있게 되어
REM 다음 5분 실행이 전부 막히므로, 반드시 rebase를 중단시켜 원상복구한다.
echo [GIT][ERROR] rebase --continue failed, aborting rebase to unblock next run>>task_run_log.txt
git rebase --abort >>task_run_log.txt 2>&1
goto :restore_stash_then_gitfail

:push
echo [GIT] push origin main>>task_run_log.txt
git push origin main >>task_run_log.txt 2>&1
if errorlevel 1 goto :restore_stash_then_gitfail

call :popstash
echo [%date% %time%] END - SUCCESS>>task_run_log.txt
echo.>>task_run_log.txt
exit /b 0

:restore_stash_then_gitfail
call :popstash
goto :gitfail

:popstash
echo [GIT] restore stashed changes>>task_run_log.txt
git stash pop --quiet >>task_run_log.txt 2>&1
goto :eof

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
