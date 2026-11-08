# Read-only инвентарь Life-OS и граница Vitalis

Фактическая Life-OS портала находится в runtime-БД `st8dom-site`. Репозиторий
`Life-Os/data/demo-vault` не является её копией.

Инвентарь запускается на сервере портала в read-only режиме:

```bash
python -m scripts.export_vitalis_lifeos \
  --output /private/path/lifeos-vitalis.json
```

## Политика schema 2

- `approved_records` всегда пуст;
- опубликованные статьи портала учитываются только в `portal_articles_excluded`;
- записи `LifeOSMaterial` из `science-neuro` перечисляются в `candidates` без тела;
- команда не одобряет, не отклоняет и не удаляет кандидатов;
- `automatic_ingestion=false`.

Vitalis допускает в RAG только проверенные полные тексты клинических рекомендаций,
которые поступают по отдельному официальному pipeline. Медицинская редактура или
публикация статьи на портале не делает её источником Vitalis.

Команда не изменяет БД, не выводит секреты и не делает сетевых запросов. Полученный JSON
используется только для аудита границы, а не как пакет знаний.

Production-деплой хранит свежий файл только на VPS в
`/srv/st8dom/private/lifeos-vitalis.json` с правами `600`. В GitHub Actions выводятся
только количества `approved` (ожидается `0`), `portal_articles_excluded` и `candidates`;
тела статей через workflow не передаются.
