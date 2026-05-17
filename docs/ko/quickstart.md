# 빠른 시작 (Quickstart) — AO Operator

> 이 문서는 영문판의 번역입니다. 차이가 있을 경우 영문판을 기준으로 합니다:
> [`../../README.md`](../../README.md)의 "Paste Into Codex Or Claude Code" 섹션

이 페이지는 Codex CLI 또는 Claude Code에서 AO Operator를 시범 사용하여,
샘플 SDD를 실체화하고 증거를 확인하는 가장 짧은 경로를 안내합니다.

## Codex / Claude Code에 붙여넣기 (Paste Into Codex or Claude Code)

명령을 shell에 직접 붙여넣지 마십시오. 새 체크아웃을 생성할 수 있는 부모
디렉토리에서 **Codex CLI** 또는 **Claude Code**를 열고, 다음 프롬프트를
그대로 붙여넣으십시오:

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

## 샘플 SDD 실체화 (Materialize a Sample SDD)

shell에서 직접 실행할 때는 Python 3과 `git`이 필요합니다:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

`--provider-free`를 지정하면, Codex / Claude API 비용 없이 인제스트
경로를 시범 사용할 수 있습니다.

## 역할 그래프와 RunSpec 확인

실행이 완료되면 AO Operator는 다음 산출물을 생성합니다:

- `runs/<run-id>/role-graph.json` — 해당 SDD에서 파생된 역할 계약 그래프
- `runs/<run-id>/runspec.yaml` — AO Runtime이 실제로 실행한 DAG 사양
- `runs/<run-id>/status/` — 각 역할이 제출한 상태 산출물
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — 감사 가능한 증거 아카이브

## 종결자 수용 (Closer Acceptance)

각 역할이 제출한 증거의 수용 여부를 판정하는 역할이 "종결자 (Closer)"입니다.
종결자의 판정은 `runs/<run-id>/status/closer/` 아래에 저장됩니다. 거부될
경우, 누락된 구체적인 증거가 사유로 명시되어 추적이 가능합니다.

## 다음 단계 (Next Steps)

- [`./getting-started.md`](./getting-started.md) — 자세한 설정
- [`./TRANSLATION.md`](./TRANSLATION.md) — 용어집
- [`../../SETUP.md`](../../SETUP.md) — 영문 설정 단계
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 일반적인 프롬프트 샘플
- [`../../profiles/README.md`](../../profiles/README.md) — 프로파일 스키마
