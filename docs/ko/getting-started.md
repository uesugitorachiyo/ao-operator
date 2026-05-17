# 시작하기 (Getting Started) — AO Operator

> 이 문서는 영문판의 번역입니다. 차이가 있을 경우 영문판을 기준으로 합니다:
> [`../../SETUP.md`](../../SETUP.md)

이 페이지는 로컬 개발 머신에서 AO Operator를 설정하고, 첫 번째 SDD 샘플을
실체화하는 최소 단계를 안내합니다.

## 사전 요구 사항 (Prerequisites)

- **운영 체제**: macOS, Ubuntu, 또는 Windows (WSL2 권장)
- **Python**: 3.10 이상
- **git**
- **선택적 provider**: Codex CLI 또는 Claude Code (provider-free 모드로 시범
  사용할 때는 불필요)
- **선택 사항**: AO Runtime 로컬 설치 (`--engine ao` 로 실행할 때 필요)

## 설치 (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# 가상 환경 생성 (권장)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 개발 의존성 설치
python -m pip install -r requirements-dev.txt
```

자세한 provider 설정 (API 키와 CLI 바이너리 경로 등)은
[`../../SETUP.md`](../../SETUP.md)를 참조하십시오.

## 검증 (Verify)

스모크 테스트를 실행합니다:

```bash
python -m pytest -q
```

이 명령은 AO Operator의 역할 계약, RunSpec 생성, 상태 산출물의 내부
일관성을 포괄적으로 검증합니다 (CI와 동일한 테스트).

## 샘플 SDD 인제스트 (Materialize a Sample SDD)

provider-free 모드로 샘플 SDD를 실체화합니다:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

산출물은 `runs/<run-id>/` 아래에 저장됩니다. 자세한 내용은
[`./quickstart.md`](./quickstart.md)를 참조하십시오.

## 다음 단계 (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Codex / Claude Code에서 AO Operator를
  시범 사용하는 단계
- [`./TRANSLATION.md`](./TRANSLATION.md) — 용어집과 번역 방침
- [`../../SETUP.md`](../../SETUP.md) — 자세한 설정 (영문)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — 일반적인 프롬프트
  샘플 (영문)
- [`../../profiles/README.md`](../../profiles/README.md) — 프로파일 스키마 (영문)
