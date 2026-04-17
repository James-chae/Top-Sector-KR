# LEADING_SECTOR_OPERATING_RULES.md

## 목표
Top-Sector-KR 대시보드가 매일 자동으로, 제시간에, 문제 없이 업데이트되고 돌아가야 한다.

## 기준선 파일
- 프론트 기준선: app/index.html
- KR 자동 실행: scripts/run_kr_pipeline.py
- KR 시간 검증: scripts/check_schedule_window.py

## KR 운영 규칙
- 07:50 KST: reset / 전환 준비
- 08:00~19:55 KST: 5분 단위 갱신
- 20:00 KST: 최종 반영
- 이후 keep

## JSON 운영 원칙
- data/*.json 은 결과물이다
- JSON 은 merge 대상이 아니다
- JSON 충돌 발생 시 수동 병합 금지
- 원칙은 삭제 -> 재생성 -> 반영

## 수정 우선순위
1. 운영 시간표
2. 실행 흐름
3. 데이터 안정성
4. 섹터 매핑 원칙
5. 프론트 UI
6. 미세 튜닝

## 작업 방식 원칙
- 복구와 개선을 한 번에 섞지 않는다
- 먼저 기준 문서와 현재 코드가 일치하는지 확인한다
- 그 다음 최소 구조부터 만든다
- 그 다음 로컬 확인
- 그 다음 GitHub 반영
- 그 다음 Actions 검증 순으로 진행한다

## 매일 새 창 시작 원칙
새 대화창에서는 아래 문서를 먼저 기준으로 둔다.
- PROJECT_BOOTSTRAP.md
- LEADING_SECTOR_OPERATING_RULES.md
- SECTOR_MAPPING_RULES.md
- DATA_PIPELINE_RULES.md
