# Постобработка OCR паспорта РФ

Решение тестового задания по постобработке и бинарной классификации (accept/reject) распознанных паспортов РФ.

## Структура репозитория

```
.
├── postprocess.py            # Основной скрипт постобработки и принятия решений
├── evaluate.py               # Скрипт валидации качества решения
├── answers.jsonl             # Итоговые предсказания для test_predictions.jsonl (2000 документов)
├── REPORT.md                 # Полный аналитический отчёт о проделанной работе и выводах
├── data/
│   ├── train_predictions.jsonl
│   ├── train_labels.jsonl
│   └── test_predictions.jsonl
└── reference/
    ├── subdivisions.csv      # Справочник подразделений (DaData)
    └── SOURCE.txt
```

## Требования к окружению

- Python 3.8+
- Стандартная библиотека Python (`json`, `csv`, `re`, `datetime`, `os`, `sys`)
- Никаких сторонних библиотек не требуется (Zero external dependencies)
- Работает полностью на CPU, без интернета

## Запуск

### 1. Генерация `answers.jsonl` для test
```bash
python postprocess.py data/test_predictions.jsonl answers.jsonl
```

### 2. Запуск на train и оценка качества
```bash
python postprocess.py data/train_predictions.jsonl train_answers.jsonl
python evaluate.py train_answers.jsonl data/train_labels.jsonl
```

## Результаты и прогноз

- **Документов в test:** 2000
- **Принято (`accept`):** 591 (29.5%)
- **Отклонено (`reject`):** 1409 (70.5%)
- **Прогноз реальных ошибок OCR:** 0 документов (0.0%)
- **Прогноз формальных расхождений из-за шума человеческой разметки (~0.8%):** 4–5 документов
- **Прогнозируемая точность (Accuracy по evaluate.py):** >= 99.2%
