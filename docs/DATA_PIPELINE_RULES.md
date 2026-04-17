# DATA_PIPELINE_RULES.md

## 목적
데이터 생성과 표시를 완전히 분리한다.

## 구조
latest_krx.json
→ market_raw.json
→ leader_board.json
→ sector_calendar_history.json
→ dashboard

## 원칙

### 1. 프론트는 계산 금지
- JSON 그대로 출력

### 2. 모든 JSON 동일 흐름 생성
- 수집
- 가공
- 점수
- 달력 누적

### 3. 상태 포함 필수
- session_state
- generated_at

### 4. 단일 진실 유지
- 프론트 merge 금지
- 부분 갱신 금지
- 화면은 최종 JSON만 본다

## 실패 처리

### 데이터 없음
- 이전 정상 데이터 유지 가능 여부를 별도 판단
- 무조건 프론트 보정하지 않는다

### 일부만 갱신
- 실패로 간주
- 전체 파이프라인 재실행 우선

### 전체 실패
- 잘못된 데이터보다 없는 데이터가 낫다
- 실패 로그를 먼저 확인한다

## 금지
- JSON 시간 불일치
- 프론트 임시 계산
- 수집/가공/점수 결과 혼합

## 목표
데이터는 항상 하나의 진실만 가진다.
