# 번역 가이드 및 용어집 (Translation Guide & Glossary)

이 디렉토리(`docs/ko/`)는 AO Operator 문서의 한국어판입니다. 원본은 영문판을
기준으로 합니다.

## 번역 방침 (Translation Policy)

1. **원본 우선 (Source of Truth)**.
2. **코드와 식별자는 번역하지 않음**: `RunSpec`, `SDD`, `factory_run`, CLI
   옵션, 파일 경로 등은 원문을 유지합니다.
3. **공식 문어체**.
4. **기존 번역 우선, 신규 음역은 신중하게**.

## 용어집 (Glossary)

| English | 한국어 | 비고 (Notes) |
| --- | --- | --- |
| Operator | 운영 계층 / Operator | 제품명(AO Operator)은 번역하지 않음 |
| Role contract | 역할 계약 | |
| RunSpec | RunSpec | 번역하지 않음 |
| SDD | SDD (사양 주도 문서) | 첫 등장 시 괄호 주기 |
| Evidence pack | 증거 팩 | 고정 번역 |
| Closer | 종결자 | 역할명 |
| Profile | 프로파일 / Profile | |
| Provider dispatch | 공급자 분배 | |
| Smoke test | 스모크 테스트 | |
| Status artifact | 상태 산출물 | |
| Approval ticket | 승인 티켓 / Approval ticket | |

## 번역 우선 순서 (Translation Priority)

1. `README.md` 도입부 (약 3 단락)
2. `SETUP.md`
3. `README.md`의 "Paste Into Codex Or Claude Code" 섹션
4. `docs/contracts/` 하위의 주요 역할 계약
5. 그 외

## 시작하기 전 점검 (Before You Start)

- 원본의 최신 버전 확인
- 중요한 용어가 미등록인 경우, 위 표에 추가
- 번역 완료 후 `<!-- TRANSLATION PENDING -->` 표시 삭제
