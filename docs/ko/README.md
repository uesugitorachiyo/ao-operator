# AO Operator

[English](../../README.md) | [日本語](../ja/README.md) | [简体中文](../zh-Hans/README.md) | [繁體中文](../zh-Hant/README.md) | **한국어** | [Español](../es/README.md) | [Русский](../ru/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md) | [Português](../pt/README.md)

> AO는 **AI Orchestration Operation (AI 오케스트레이션 운영)** 의 약어입니다.
> 제품명: **AO Operator**. GitHub 저장소 슬러그: `ao-operator`.

> 이 문서는 영문 원본의 번역입니다. 차이가 있는 경우 영문판을 기준으로 합니다:
> [`../../README.md`](../../README.md)

![AO Operator 자율 에이전트 CLI](../../images/ao-operator-agent-team.svg)

**AO Operator는 AI 오케스트레이션 운영 계층입니다. 자연어로 목표를 기술하면
Codex 또는 Claude Code를 구동하여, 작업을 검증된 산출물까지 끌고 갑니다.**
제품 요구사항, SDD, 또는 작업 개요를 제공하면 AO Operator는 이를 범위가
정의된 역할, 크로스 플랫폼 검사, RunSpec, 상태 산출물, 검토 가능한 증거로
변환합니다.

"AI CLI가 작업을 완료하도록 만들고 싶지, 돌봐야 할 채팅 기록 더미를 남기고
싶지는 않다"는 분이라면 여기서 시작하십시오. AO Operator는 결과 지향 작업을
대상으로 합니다: 엔지니어링 사양으로부터 애플리케이션 샘플을 생성하고,
저장소를 지속적으로 개선하며, macOS / Ubuntu / Windows에서 동작을 검증하고,
종결자(Closer)가 실행 결과를 수용하기 전까지 각 역할에 증거 제출을 요구합니다.

AO Operator는 동시에 더 넓은 AO 어댑터 면(surface)을 위한 제품 계층이기도
합니다. OpenClaw는 작업의 투입, 스케줄링, 관측을 담당하고; Hermes 스타일 큐는
worker 포화 실행을 구동하며; AO Runtime은 하부에서 공급자 분배, 정책, 이벤트,
증거를 제공합니다. AO Operator는 이러한 플러그인 / 어댑터 흐름에 통일된 역할
계약을 제공하여, 각 통합이 자체적으로 워크플로 의미론을 발명하지 않도록
합니다.

## Codex / Claude Code에 붙여넣기 (Paste Into Codex Or Claude Code)

shell 명령을 터미널에 직접 붙여넣지 마십시오. 평소 사용하는 AI CLI에서
시작하십시오. 새로운 체크아웃을 만들 수 있는 부모 디렉토리에서
**Codex CLI** 또는 **Claude Code**를 열고 다음 프롬프트를 붙여넣으십시오:

```text
실시간 provider 토큰을 사용하지 않고 AO Operator를 시범 사용한다.

목표:
- 아직 없다면 https://github.com/uesugitorachiyo/ao-operator.git 을 clone.
- 저장소로 진입.
- examples/ingestible-specs/financial-citation-audit-sdd.md 를 읽기.
- provider 없는 인제스트 경로로 smoke-test 프로파일을 사용해 SDD 를 실체화.
- OPENAI_API_KEY 와 ANTHROPIC_API_KEY 를 설정하지 않기.
- Python 3 또는 git 이 없으면, 중단하고 이유 설명.

보고할 내용:
- SDD 가 요구한 워크플로 결과
- AO Operator 가 증명한 공개 진입점
- AO Operator 가 만든 역할 그래프
- 생성된 RunSpec 경로
- 상태 디렉토리 경로
```

(더 많은 원문 내용은 [`../../README.md`](../../README.md) 참조)

## 개요 (Overview)

AO Operator는 SDD (사양 주도 문서) 또는 자연어 작업 개요를 받아,
**역할 계약 (role contracts)** 을 바탕으로 Codex / Claude Code 같은 여러
에이전트가 협업하도록 하여, 검증된 산출물(코드, 문서, 증거 팩)을 생성합니다.
제품의 핵심은 다음 세 가지입니다:

1. **역할 계약**: 각 에이전트가 "무엇을 출력해야 하는지"를 정의하며,
   평가자는 이를 기준으로 수용 여부를 판단합니다.
2. **RunSpec**: 작업을 실행 가능한 DAG로 표현하여, AO Runtime 위에서
   재현 가능하게 실행됩니다.
3. **증거 팩**: 실행 이력, 산출물, 서명을 하나의 감사 가능한 아카이브로
   고정합니다.

## 빠른 시작 (Quickstart)

자세한 단계는 [`./quickstart.md`](./quickstart.md)를 참조하십시오. 설치는
[`./getting-started.md`](./getting-started.md)를 참조하십시오.

## 라이선스 (License)

AO Operator는 다음 중 하나의 라이선스로 제공되며, 사용자가 선택할 수 있습니다:

- [Apache License, Version 2.0](../../LICENSE-APACHE)
- [MIT License](../../LICENSE-MIT)

자세한 내용은 [`NOTICE`](../../NOTICE)를 참조하십시오.

귀하가 명시적으로 다르게 진술하지 않는 한, 본 프로젝트에 의도적으로
제출하는 기여는 Apache-2.0 라이선스의 정의에 따라, 추가 조건 없이 위의
이중 라이선스 형태로 제공됩니다.

## 이 번역에 대해 (About This Translation)

이 한국어판은 단계적으로 추가되고 있습니다. 용어집과 번역 방침은
[`./TRANSLATION.md`](./TRANSLATION.md)를 참조하십시오. 영문 원본과 차이가
있는 경우, 영문판을 기준으로 합니다.
