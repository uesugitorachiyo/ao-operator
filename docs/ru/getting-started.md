# Начало работы (Getting Started) — AO Operator

> Настоящий документ является переводом англоязычной версии. При наличии расхождений
> авторитетной считается англоязычная версия:
> [`../../SETUP.md`](../../SETUP.md)

На этой странице описана минимальная последовательность действий, чтобы развернуть
AO Operator на локальной машине разработчика и материализовать первый пример SDD.

## Предварительные требования (Prerequisites)

- **Операционная система**: macOS, Ubuntu или Windows (рекомендуется WSL2)
- **Python**: 3.10 или более новая версия
- **git**
- **Провайдер (по желанию)**: Codex CLI или Claude Code (не требуется, если Вы
  собираетесь опробовать режим provider-free)
- **По желанию**: локальная установка AO Runtime (необходима для запуска с
  `--engine ao`)

## Установка (Install)

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator

# Создайте виртуальное окружение (рекомендуется)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

# Установите зависимости для разработки
python -m pip install -r requirements-dev.txt
```

Подробные сведения о настройке провайдеров (ключей API, путей к бинарникам CLI и
т. п.) см. в [`../../SETUP.md`](../../SETUP.md).

## Проверка работоспособности (Verify)

Запустите дымовые тесты:

```bash
python -m pytest -q
```

Эта команда комплексно проверяет согласованность ролевых контрактов AO Operator,
порождение RunSpec и артефактов статуса (это тот же набор тестов, что выполняется в
CI).

## Материализация примера SDD (Materialize a Sample SDD)

Материализуйте пример SDD в режиме без провайдера:

```bash
python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

Артефакты сохраняются в каталоге `runs/<run-id>/`. Подробности см. в
[`./quickstart.md`](./quickstart.md).

## Следующие шаги (Next Steps)

- [`./quickstart.md`](./quickstart.md) — Порядок опробования AO Operator из Codex или
  Claude Code
- [`./TRANSLATION.md`](./TRANSLATION.md) — Глоссарий и принципы перевода
- [`../../SETUP.md`](../../SETUP.md) — Подробная инструкция по установке (на
  английском языке)
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Часто используемые примеры
  запросов (на английском языке)
- [`../../profiles/README.md`](../../profiles/README.md) — Схема профилей (на
  английском языке)
