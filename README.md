# Top-Sector-KR

한국 주도주 / 주도섹터 / 주도섹터 달력 / 한국일정(UI 최소판) 전용 대시보드 프로젝트입니다.

## 프로젝트 목표

기존 프로젝트는 workflow와 자동화가 많이 꼬였기 때문에,
이 저장소는 한국 전용 최소 기능 구조로 처음부터 다시 만드는 것을 목표로 합니다.

1차 범위:
- 한국 주도섹터
- 한국 주도주
- 주도섹터 달력
- 한국일정 UI 최소판
- 로컬 먼저 완성
- GitHub 반영
- 이후 GitHub Actions 5분 자동화 검증

US 기능은 1차 범위에서 제외합니다.

## 운영 시간 규칙

- 07:50 KST : reset
- 08:00 ~ 19:55 KST : 5분 갱신
- 20:00 KST : 최종 반영
- 20:00 이후 : keep

## 폴더 구조

```text
Top-Sector-KR/
├─ app/
│  ├─ index.html
│  ├─ app.css
│  └─ app.js
├─ scripts/
│  ├─ check_schedule_window.py
│  ├─ fetch_latest_krx.py
│  ├─ build_market_raw.py
│  ├─ score_leaders.py
│  ├─ update_sector_calendar.py
│  └─ run_kr_pipeline.py
├─ data/
├─ config/
├─ docs/
└─ .github/workflows/
```

## 데이터 파이프라인

```text
Naver 수집
→ latest_krx.json
→ market_raw.json
→ leader_board.json
→ sector_calendar_history.json
→ dashboard
```

## 핵심 원칙

- 프론트는 계산하지 않고 JSON을 그대로 출력
- 데이터 생성과 화면 출력을 분리
- JSON은 merge 대상이 아님
- 로컬 확인 후 GitHub 반영
- workflow 문제와 화면 문제를 섞지 않음

## 실행 순서

### 1. 시간 규칙 확인
```powershell
python .\scripts\check_schedule_window.py
```

### 2. 전체 파이프라인 실행
```powershell
python .\scripts\run_kr_pipeline.py
```

### 3. 로컬 서버 실행
```powershell
python -m http.server 5500
```

### 4. 브라우저 확인
```text
http://127.0.0.1:5500/app/index.html
```

## 필수 파일

- `config/섹터_마스터.xlsx`
- `data/krx_holidays.json` (있으면 사용, 없어도 주말 기준 동작)

## 다음 단계

1. 로컬 최종 점검
2. GitHub repo `Top-Sector-KR` 초기 반영
3. workflow 1개만 생성
4. schedule이 실제 생성되는지 검증
5. 자동화 검증 완료 후 기능 확장
