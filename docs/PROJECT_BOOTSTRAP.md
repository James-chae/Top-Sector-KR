# PROJECT_BOOTSTRAP.md

## 프로젝트명
Top-Sector-KR

## 로컬 경로
C:\Users\solom\OneDrive\바탕 화면\Top Sector\Top-Sector-KR

## GitHub Repo
Top-Sector-KR

---

## 1. 프로젝트 목표

기존 Leading Sector 프로젝트는 workflow와 자동화가 많이 꼬였기 때문에,
이번 프로젝트는 한국 주도주/주도섹터 전용 대시보드를 새 구조로 처음부터 다시 만든다.

1차 목표:
- 한국 주도섹터
- 한국 주도주
- 주도섹터 달력
- 현재 대시보드의 디자인 톤 유지
- 로컬 먼저 완성
- 이후 GitHub 반영
- 이후 GitHub Actions 5분 자동화 검증
- 자동화가 검증된 뒤에만 기능 확장

US 기능은 1차 범위에서 제외한다.

---

## 2. 운영 시간 규칙

- 07:50 KST : reset
- 08:00 ~ 19:55 KST : 5분 갱신
- 20:00 KST : 최종 반영
- 20:00 이후 : keep

---

## 3. 작업 원칙

1. 기존 프로젝트는 보존한다.
2. 새 프로젝트 폴더 / 새 GitHub repo 로 시작한다.
3. 데이터 수집 → 점수 계산 → 달력 누적 → 화면 출력 순서로 만든다.
4. 로컬에서 먼저 확인한다.
5. GitHub 반영은 로컬 검증 뒤에만 한다.
6. workflow 문제와 화면 문제를 섞지 않는다.
7. 자동화는 가장 먼저 “실제로 schedule 이 생성되고 실행되는지” 검증한다.
8. 문제 발생 시 바로 직전 단계 백업본으로 복구한다.
9. 전체 수정본 파일 방식으로만 작업한다.
10. 매 단계마다 파일 교체 명령어 / 로컬 실행 명령어 / 로컬 확인 주소를 함께 남긴다.

---

## 4. 1차 MVP 범위

### 포함
- latest_krx 수집
- market_raw 생성
- leader_board 생성
- sector_calendar_history 생성
- index 화면 출력
  - 주도주
  - 상위 주도섹터
  - 주도섹터 달력

### 제외
- 미국종목
- 미국일정
- 한국일정
- 전체시장
- 한국종목 개별 탭
- 수동 일정 입력
- 달력 수동 override
- 복잡한 멀티탭 구조
- 확장용 이벤트/보조 차트

---

## 5. 데이터 파이프라인

Naver 수집
→ data/latest_krx.json
→ data/market_raw.json
→ data/leader_board.json
→ data/sector_calendar_history.json
→ app/index.html 출력

원칙:
- 프론트는 계산하지 않는다.
- 프론트는 JSON만 출력한다.
- 모든 주요 JSON에는 generated_at / session_state 를 넣는다.
- 부분 갱신보다 전체 재생성이 우선이다.

---

## 6. 섹터 원칙

엑셀 원본:
- config/섹터_마스터.xlsx

최종 계산 원칙:
- sector2 값이 있으면 sector2 사용
- 없으면 sector1 사용

즉:
- final_sector = sector2 if sector2 exists else sector1

market_raw 규칙:
- sector1 = 최종 계산용 섹터
- sector2 = 엑셀 원본 sector2 참고값

---

## 7. 폴더 구조

Top-Sector-KR/
├─ app/
│  ├─ index.html
│  ├─ app.js
│  └─ app.css
├─ scripts/
│  ├─ fetch_latest_krx.py
│  ├─ build_market_raw.py
│  ├─ score_leaders.py
│  ├─ update_sector_calendar.py
│  ├─ run_kr_pipeline.py
│  └─ check_schedule_window.py
├─ data/
│  ├─ latest_krx.json
│  ├─ market_raw.json
│  ├─ leader_board.json
│  ├─ sector_calendar_history.json
│  ├─ latest_leaders_snapshot.json
│  ├─ previous_leaders_snapshot.json
│  ├─ latest_d1_snapshot.json
│  ├─ previous_d1_snapshot.json
│  └─ krx_holidays.json
├─ config/
│  └─ 섹터_마스터.xlsx
├─ docs/
│  ├─ PROJECT_BOOTSTRAP.md
│  ├─ LEADING_SECTOR_OPERATING_RULES.md
│  ├─ SECTOR_MAPPING_RULES.md
│  ├─ DATA_PIPELINE_RULES.md
│  └─ DEPLOY_CHECKLIST.md
├─ .github/
│  └─ workflows/
│     └─ update-kr-dashboard.yml
├─ requirements.txt
├─ .gitignore
└─ README.md

---

## 8. 단계별 진행 순서

### Step 1
프로젝트 기준선 문서와 폴더 구조 확정

### Step 2
check_schedule_window.py 작성
- 07:49
- 07:55
- 08:05
- 19:55
- 20:00
시간 테스트 먼저

### Step 3
fetch_latest_krx.py 작성
- 기존 검증된 Naver 수집 로직만 이식

### Step 4
build_market_raw.py 작성
- latest + 엑셀 매핑
- ETF 필터
- final_sector 규칙 반영

### Step 5
score_leaders.py 작성
- 상위 주도섹터
- 오늘의 주도주
- 눌림목
- D-1 / D-2 최소판

### Step 6
update_sector_calendar.py 작성
- sector_calendar_history 누적

### Step 7
app/index.html / app.js / app.css 작성
- 주도주
- 상위 주도섹터
- 주도섹터 달력
- 현재 디자인 톤 유지
- US 제거

### Step 8
run_kr_pipeline.py 작성
- 수집 → 가공 → 점수 → 달력 순서 통합

### Step 9
로컬 검증
- JSON 생성 확인
- index 확인

### Step 10
GitHub 반영

### Step 11
GitHub Actions workflow 1개만 생성
- schedule 생성 확인
- Actions 실행 여부 확인
- 실제 5분 단위 동작 검증

### Step 12
자동화 검증 완료 후 기능 확장

---

## 9. 절대 금지

- 기존 프로젝트 통째 복붙
- 처음부터 workflow 여러 개 생성
- 화면 문제와 자동화 문제를 동시에 수정
- 로컬 확인 없이 push
- JSON merge로 해결
- 문서 기준 없이 섹터 원칙 변경

---

## 10. 이번 프로젝트의 기준 참조 자산

강한 참조:
- generate_latest_krx_from_naver.py
- build_market_raw_from_latest_krx.py
- run_scoring.py
- run_scoring_auto.py
- update_sector_calendar_history.py
- 현재 index.html 디자인 요소

기준 문서:
- LEADING_SECTOR_OPERATING_RULES.md
- SECTOR_MAPPING_RULES.md
- DATA_PIPELINE_RULES.md

보조 문서:
- DEPLOY_CHECKLIST.md
- Leading_Sector_운영매뉴얼.md
