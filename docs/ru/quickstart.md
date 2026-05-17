# Быстрый старт (Quickstart) — AO Operator

> Настоящий документ является переводом англоязычной версии. При наличии расхождений
> авторитетной считается англоязычная версия:
> раздел "Paste Into Codex Or Claude Code" в [`../../README.md`](../../README.md)

На этой странице описан кратчайший путь опробования AO Operator из Codex CLI или
Claude Code: материализация примера SDD и просмотр свидетельств.

## Вставка в Codex или Claude Code (Paste Into Codex or Claude Code)

Не вводите команды непосредственно в оболочке. Откройте **Codex CLI** или **Claude
Code** в родительском каталоге, в котором допустимо создать новый клон, и вставьте
приведённый ниже запрос дословно:

```text
Попробуйте AO Operator, не используя действующие провайдерские токены.

Цели:
- Если репозиторий ещё не получен, клонируйте
  https://github.com/uesugitorachiyo/ao-operator.git.
- Перейдите в этот репозиторий.
- Прочитайте examples/ingestible-specs/financial-citation-audit-sdd.md.
- Материализуйте указанный SDD в качестве профиля smoke-test, используя путь
  загрузки без провайдера.
- Не задавайте переменные OPENAI_API_KEY и ANTHROPIC_API_KEY.
- Если Python 3 или git отсутствуют, остановитесь и поясните причину.

Сообщите:
- Какие результаты рабочего процесса требует SDD
- Какой публичный клин демонстрирует AO Operator
- Какой ролевый граф построил AO Operator
- Путь к сгенерированному RunSpec
- Путь к каталогу состояния
```

## Материализация примера SDD (Materialize a Sample SDD)

Если Вы хотите запустить процесс непосредственно из оболочки, воспользуйтесь
приведёнными ниже командами. Требуются Python 3 и `git`:

```bash
git clone https://github.com/uesugitorachiyo/ao-operator.git
cd ao-operator
python -m pip install -r requirements-dev.txt

python scripts/factory_run.py \
    --profile smoke-test \
    --spec examples/ingestible-specs/financial-citation-audit-sdd.md \
    --provider-free
```

При указании `--provider-free` отрабатывается только путь приёма (ingestion), что
позволяет опробовать процесс без расходов на вызовы API Codex или Claude.

## Просмотр ролевого графа и RunSpec

По завершении выполнения AO Operator формирует следующие артефакты:

- `runs/<run-id>/role-graph.json` — граф ролевых контрактов, выведенный из SDD
- `runs/<run-id>/runspec.yaml` — спецификация DAG, исполняемая AO Runtime
- `runs/<run-id>/status/` — артефакты статуса, оставленные каждой ролью
- `runs/<run-id>/evidence-pack-<run-id>.tar.zst` — аудируемый архив свидетельств

## Проверка приёмки клозера (Closer Acceptance)

Роль «клозер» принимает решение о том, является ли предъявленная каждой ролью
свидетельская база приемлемой. Решение клозера сохраняется в
`runs/<run-id>/status/closer/`. При отказе в приёмке перечисляются конкретные
недостающие свидетельства, что упрощает поиск первопричины.

## Следующие шаги (Next Steps)

- [`./getting-started.md`](./getting-started.md) — Подробная настройка окружения
- [`./TRANSLATION.md`](./TRANSLATION.md) — Глоссарий
- [`../../SETUP.md`](../../SETUP.md) — Инструкция по установке на английском языке
- [`../../PROMPT_SAMPLES.md`](../../PROMPT_SAMPLES.md) — Часто используемые примеры
  запросов
- [`../../profiles/README.md`](../../profiles/README.md) — Схема профилей
