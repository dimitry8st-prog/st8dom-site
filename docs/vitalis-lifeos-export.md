# Контролируемый экспорт Life-OS в Vitalis

Фактическая Life-OS портала находится в runtime-БД `st8dom-site`. Репозиторий
`Life-Os/data/demo-vault` не является её копией.

Экспорт запускается на сервере портала в read-only режиме:

```bash
python -m scripts.export_vitalis_lifeos \
  --output /private/path/lifeos-vitalis.json
```

В `approved_records` попадают только опубликованные медицинские статьи раздела
неврологии/нейрохирургии, у которых указаны медицинский рецензент, дата проверки и
HTTPS-источники. Материалы `LifeOSMaterial` из потока `science-neuro` попадают только в
`candidates` без тела и со статусом `needs_medical_review`.

Команда не изменяет БД, не выводит секреты и не делает сетевых запросов. Полученный JSON
передаётся в офлайн-import Vitalis. Его нельзя размещать в публичном Git или использовать
как автоматическое медицинское одобрение.

Production-деплой хранит свежий экспорт только на VPS в
`/srv/st8dom/private/lifeos-vitalis.json` с правами `600`. В GitHub Actions выводятся
только количества `approved` и `candidates`; тела статей через workflow не передаются.
Файл остаётся staging-артефактом для явной проверки и не импортируется в Vitalis
автоматически.
