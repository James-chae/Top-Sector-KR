# SECTOR_MAPPING_RULES.md

## 목표
섹터 매핑은 사람이 수정하는 엑셀 원본과 운영용 JSON 반영 흐름을 분리해 안정적으로 관리한다.

## 원본 / 운영 파일 정의
- 편집 원본: config/섹터_마스터.xlsx
- 실제 대시보드 입력: data/market_raw.json
- 최종 점수/주도주 결과: data/leader_board.json

## 최종 섹터 반영 원칙
가장 중요한 원칙:
- sector2 값이 있으면 sector2를 최종 계산용 섹터로 사용
- sector2 값이 없으면 sector1을 최종 계산용 섹터로 사용

즉:

final_sector = sector2 if sector2 exists else sector1

## market_raw 반영 규칙
- data/market_raw.json 의 sector1 에는 최종 계산용 섹터(final_sector)를 넣는다
- data/market_raw.json 의 sector2 에는 엑셀의 sector2 원본 값을 그대로 보조 정보로 넣는다

정리:
- sector1 = 계산 기준
- sector2 = 참고용 보조 정보

## 엑셀 수정 후 실행 순서
1. config/섹터_마스터.xlsx 수정
2. python scripts/build_market_raw.py
3. python scripts/score_leaders.py
4. python scripts/update_sector_calendar.py
5. 로컬 확인
6. GitHub 반영

## 로컬 확인
python -m http.server 5500

브라우저:
http://127.0.0.1:5500/app/index.html

## 절대 금지
- 섹터 원칙을 문서 없이 즉흥적으로 바꾸지 않는다
- JSON 충돌을 merge로 해결하지 않는다
- 기준선 없이 구조를 뒤집지 않는다
