#!/usr/bin/env python3
"""Постобработка OCR паспортов РФ.

Запуск:
    python postprocess.py <input_predictions.jsonl> <output_answers.jsonl>

Требования:
    - Работает на CPU, без интернета, без сторонних зависимостей (только стандартная библиотека Python 3).
    - Принимает максимально возможное количество документов с околонулевым уровнем ошибок (Precision ~ 99.2%+).
    - Проверяет действительность паспорта на 01.10.2026.
"""

import sys
import os
import json
import csv
import re
from datetime import date, timedelta

FIELDS = [
    "Last_name_ru", "First_name_ru", "Middle_name_ru", "Sex_ru", "Birth_date",
    "Birth_place_ru", "Issue_date", "Issue_organisation_code", "Licence_number",
    "Issue_organization_ru"
]

REF_DATE = date(2026, 10, 1)

TRANSLIT_REV = {
    'A': 'А', 'B': 'Б', 'V': 'В', 'G': 'Г', 'D': 'Д', 'E': 'Е', '2': 'Ё',
    'J': 'Ж', 'Z': 'З', 'I': 'И', 'Q': 'Й', 'K': 'К', 'L': 'Л', 'M': 'М',
    'N': 'Н', 'O': 'О', 'P': 'П', 'R': 'Р', 'S': 'С', 'T': 'Т', 'U': 'У',
    'F': 'Ф', 'H': 'Х', 'C': 'Ц', '3': 'Ч', '4': 'Ш', 'W': 'Щ', 'X': 'Ъ',
    'Y': 'Ы', '9': 'Ь', '6': 'Э', '7': 'Ю', '8': 'Я'
}

OFFICIAL_WORDS = {
    'ОТДЕЛ', 'ОТДЕЛЕНИЕ', 'ОТДЕЛОМ', 'ВОПРОСАМ', 'МИГРАЦИИ', 'ОМВД', 'УМВД', 'МВД',
    'ГУ', 'УПРАВЛЕНИЕ', 'УПРАВЛЕНИЕМ', 'ТЕРРИТОРИАЛЬНЫЙ', 'ПУНКТ', 'ТП', 'ОФМС', 'УФМС',
    'ФМС', 'РОССИИ', 'ПО', 'В', 'И', 'Г.', 'ГОР.', 'ГОРОДЕ', 'ГОРОДСКОМ', 'ОКРУГЕ',
    'ПОСЕЛЕНИИ', 'ПОСЕЛЕНИЯ', 'ПОСЕЛКЕ', 'ПОСЁЛКЕ', 'РАЙОНЕ', 'РАЙОНА', 'Р-НЕ', 'Р-НА',
    'ОБЛАСТИ', 'ОБЛАСТЬ', 'ОБЛ', 'ОБЛ.', 'КРАЕ', 'КРАЯ', 'КРАЙ', 'РЕСПУБЛИКЕ', 'РЕСПУБЛИКА', 'РЕСП',
    'АВТОНОМНОМ', 'АВТОНОМНОЙ', 'АО', 'ЮГРЕ', 'ХМАО', 'ЯНАО', 'САНКТ-ПЕТЕРБУРГУ', 'МОСКВЕ',
    'МОСКВЫ', 'ПЕТЕРБУРГА', 'СЕВАСТОПОЛЮ', 'СЕВАСТОПОЛЕ', 'МЕЖРАЙОННЫЙ', 'МЕЖМУНИЦИПАЛЬНЫЙ',
    'МУНИЦИПАЛЬНОМ', 'МУНИЦИПАЛЬНОМУ', 'МУНИЦИПАЛЬНОГО', 'АДМИНИСТРАТИВНОМ', 'АДМИНИСТРАТИВНОМУ',
    'ЦЕНТРАЛЬНОМУ', 'СЕВЕРНОМУ', 'ЮЖНОМУ', 'ЗАПАДНОМУ', 'ВОСТОЧНОМУ', 'СЕВЕРО-ЗАПАДНОМУ',
    'СЕВЕРО-ВОСТОЧНОМУ', 'ЮГО-ЗАПАДНОМУ', 'ЮГО-ВОСТОЧНОМУ', 'НОВОМОСКОВСКОМУ', 'ТРОИЦКОМУ',
    'ЗЕЛЕНОГРАДСКОМУ', 'ДЕЛАМ', 'ВНУТРЕННИХ', 'ДЕЛ', 'МИНИСТЕРСТВО', 'МИНИСТЕРСТВОМ',
    'ПОЛИЦИИ', 'ОТДЕЛЕНИЯ', 'ПУНКТА', 'ДИСЛОКАЦИИ', 'МЕСТОМ', 'МЕСТА', 'ДЕЙСТВИЯ', 'СТ.',
    'СТАНИЦЕ', 'СТАНИЦА', 'ПОС.', 'С.', 'Д.', 'ПГТ', 'СЕЛО', 'ДЕРЕВНЯ', 'ПОСЕЛОК', 'ПОСЁЛОК',
    'РАБОЧИЙ', 'Р.П.', 'П.'
}


def norm(s):
    return " ".join(str(s or "").split()).upper()


def load_subdivision_words():
    words = set(OFFICIAL_WORDS)
    candidates = [
        os.path.join(os.path.dirname(__file__), "reference", "subdivisions.csv"),
        os.path.join(os.getcwd(), "reference", "subdivisions.csv"),
        "reference/subdivisions.csv"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None)
                    for _, name in reader:
                        for w in re.findall(r'[А-ЯЁ0-9№\.\-]+', norm(name)):
                            words.add(w.strip('.'))
                break
            except Exception:
                pass
    return words


SUBDIV_WORDS = load_subdivision_words()


def mrz_char_val(c):
    if '0' <= c <= '9': return ord(c) - ord('0')
    if 'A' <= c <= 'Z': return ord(c) - ord('A') + 10
    return 0


def calc_check_digit(s):
    weights = [7, 3, 1]
    return str(sum(mrz_char_val(c) * weights[i % 3] for i, c in enumerate(s)) % 10)


def mrz_to_cyr(s):
    parts = s.split('<')
    cyr_parts = [''.join(TRANSLIT_REV.get(c, c) for c in p) for p in parts if p]
    return ' '.join(cyr_parts)


def parse_date(d_str):
    if not d_str: return None
    try:
        parts = d_str.strip().split('.')
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except Exception:
        pass
    return None


def add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def is_passport_valid_on_ref(b_date, i_date, ref_date=REF_DATE):
    """Проверка действительности паспорта РФ на 01.10.2026."""
    if not b_date or not i_date:
        return False, "missing_date"
    if i_date > ref_date:
        return False, "future_issue"
    if i_date < b_date:
        return False, "issue_before_birth"
    
    b14 = add_years(b_date, 14)
    b20 = add_years(b_date, 20)
    b45 = add_years(b_date, 45)
    
    if i_date < b14:
        return False, "issued_before_14"
    
    # Замена в 20 лет (+90 дней grace period согласно Постановлению № 1205)
    if ref_date >= b20:
        if i_date < b20:
            if ref_date > b20 + timedelta(days=90):
                return False, "expired_at_20"
                
    # Замена в 45 лет (+90 дней grace period)
    if ref_date >= b45:
        if i_date < b45:
            if ref_date > b45 + timedelta(days=90):
                return False, "expired_at_45"

    return True, "valid"


def extract_viz_text(field_obj):
    if not field_obj:
        return ""
    lines = field_obj.get("lines", [])
    return " ".join(line.get("text", "") for line in lines).strip()


def get_field_char_confs(field_obj):
    if not field_obj or "lines" not in field_obj:
        return []
    return [c for line in field_obj["lines"] for c in line.get("char_conf", [])]


def is_suspicious_org(text):
    text = norm(text)
    words = text.split()
    if not words:
        return True, "empty"
    # Предлоги в конце
    if words[-1] in {'В', 'ПО', 'НА', 'О', 'И', 'С', 'К', 'У', 'ОТ', 'ДО'}:
        return True, "ends_with_prep"
    # Недопустимое начало
    if words[0] in {'РОССИИ', 'ОБЛАСТИ', 'ОБЛ.', 'Р-НЕ', 'РАЙОНЕ', 'КРАЯ', 'КРАЕ'}:
        return True, "bad_start"
    # Оборванное прилагательное в конце
    last = words[-1]
    if last.endswith(('СКОЙ', 'ЦКОЙ', 'СКОГО', 'ЦКОГО', 'НСКОЙ', 'НСКОГО', 'БАЛКАРСКОЙ')):
        return True, "ends_with_adj"
    if len(text) < 15:
        return True, "too_short"
    # Проверка пропущенных предлогов перед районом
    m = re.search(r'([А-ЯЁ]+СКОМ\s+(?:РАЙОНЕ|Р-НЕ))', text)
    if m:
        prefix = text[:m.start()].strip()
        p_words = prefix.split()
        if not p_words or p_words[-1] not in {'В', 'ПО'}:
            return True, "missing_prep_before_district"
    # Проверка слов по словарю подразделений
    clean_words = [w.strip('.,()') for w in words if len(w.strip('.,()')) > 1]
    unknown = [w for w in clean_words if w not in SUBDIV_WORDS and not w.isdigit()]
    if unknown:
        return True, f"unknown_words: {unknown}"
    return False, "ok"


def is_suspicious_bp(text):
    text = norm(text)
    words = text.split()
    if not words:
        return True, "empty"
    if words[-1] in {'В', 'ПО', 'НА', 'О', 'И', 'С', 'К', 'У'}:
        return True, "ends_with_prep"
    if words[0] in {'Р-НА', 'Р-НЕ', 'РАЙОНА', 'РАЙОНЕ', 'ОБЛАСТИ', 'ОБЛ.', 'КРАЯ', 'КРАЕ'}:
        return True, "bad_start"
    # Оборванное начало или конец
    if words[0].endswith(('СКОГО', 'ЦКОГО', 'НСКОГО', 'ВСКОГО')):
        return True, "starts_with_genitive_adj"
    last = words[-1]
    if last.endswith(('СКОГО', 'ЦКОГО', 'НСКОГО', 'ВСКОГО', 'СКИЙ')):
        return True, "ends_with_adj"
    if len(text) < 12 and not any(city in text for city in {'МОСКВА', 'ЛЕНИНГРАД', 'ПЕТЕРБУРГ'}):
        return True, "too_short"
    if re.search(r'([А-ЯЁ])\1{2,}', text):
        return True, "triple_char"
    if re.search(r'\b(ЧСЕВЕРНАЯ|ПРРИМОРСКОГО)\b', text):
        return True, "known_typo"
    return False, "ok"


def process_document(doc, min_conf_th=0.95):
    """Обрабатывает один документ.
    
    Возвращает dict с решением:
      {"doc_id": "...", "decision": "accept"|"reject", ["fields": {...}]}
    """
    doc_id = doc["doc_id"]
    viz = doc.get("viz") or {}
    mrz = doc.get("mrz")
    
    # 1. Проверяем наличие всех 10 полей в визуальной зоне
    if not all(viz.get(fld) is not None for fld in FIELDS):
        return {"doc_id": doc_id, "decision": "reject"}
        
    extracted = {fld: norm(extract_viz_text(viz.get(fld))) for fld in FIELDS}
    
    # Нормализация формата простых полей
    if "МУЖ" in extracted["Sex_ru"]: extracted["Sex_ru"] = "МУЖ."
    elif "ЖЕН" in extracted["Sex_ru"]: extracted["Sex_ru"] = "ЖЕН."
    
    cd_digits = "".join(c for c in extracted["Issue_organisation_code"] if c.isdigit())
    if len(cd_digits) == 6:
        extracted["Issue_organisation_code"] = f"{cd_digits[:3]}-{cd_digits[3:]}"
        
    lic_digits = "".join(c for c in extracted["Licence_number"] if c.isdigit())
    if len(lic_digits) == 10:
        extracted["Licence_number"] = f"{lic_digits[:2]} {lic_digits[2:4]} {lic_digits[4:]}"
        
    # 2. Проверка машиночитаемой зоны (MRZ)
    if not mrz or not mrz.get("lines") or len(mrz["lines"]) != 2:
        return {"doc_id": doc_id, "decision": "reject"}
        
    m1 = mrz["lines"][0].get("text", "").rstrip("<")
    m2 = mrz["lines"][1].get("text", "")
    if len(m2) < 44 or not m1.startswith("PNRUS"):
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Проверка контрольных сумм по ГОСТ / ICAO Doc 9303
    c1 = (m2[9] == calc_check_digit(m2[0:9]))
    c2 = (m2[19] == calc_check_digit(m2[13:19]))
    c3 = (m2[42] == calc_check_digit(m2[28:41]))
    c4 = (m2[43] == calc_check_digit(m2[0:10] + m2[13:20] + m2[21:43]))
    if not (c1 and c2 and c3 and c4):
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Извлечение полей из строки 2 MRZ
    s1_3 = m2[0:3]
    s4 = m2[28]
    num = m2[3:9]
    mrz_lic = f"{s1_3[:2]} {s1_3[2]}{s4} {num}"
    
    yy_b = int(m2[13:15]) if m2[13:15].isdigit() else -1
    century_b = "20" if 0 <= yy_b <= 26 else "19"
    mrz_b = f"{m2[17:19]}.{m2[15:17]}.{century_b}{m2[13:15]}"
    
    mrz_sex = "МУЖ." if m2[20] == "M" else ("ЖЕН." if m2[20] == "F" else "")
    
    yy_i = int(m2[29:31]) if m2[29:31].isdigit() else -1
    century_i = "20" if 0 <= yy_i <= 26 else "19"
    mrz_i = f"{m2[33:35]}.{m2[31:33]}.{century_i}{m2[29:31]}"
    
    mrz_code = f"{m2[35:38]}-{m2[38:41]}"
    
    # Кросс-валидация: строгое совпадение VIZ и MRZ
    if (extracted["Licence_number"] != mrz_lic or
        extracted["Birth_date"] != mrz_b or
        extracted["Issue_date"] != mrz_i or
        extracted["Issue_organisation_code"] != mrz_code or
        extracted["Sex_ru"] != mrz_sex):
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Проверка действительности паспорта на 01.10.2026
    b_dt = parse_date(extracted["Birth_date"])
    i_dt = parse_date(extracted["Issue_date"])
    is_valid, _ = is_passport_valid_on_ref(b_dt, i_dt)
    if not is_valid:
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Проверка ФИО по строке 1 MRZ
    m1_names = m1[5:].split("<<")
    mrz_last = mrz_to_cyr(m1_names[0])
    rest = m1_names[1] if len(m1_names) > 1 else ""
    rest_parts = rest.split("<")
    mrz_first = mrz_to_cyr(rest_parts[0]) if len(rest_parts) > 0 else ""
    mrz_mid = mrz_to_cyr(rest_parts[1]) if len(rest_parts) > 1 else ""
    
    if (extracted["Last_name_ru"] != mrz_last or
        extracted["First_name_ru"] != mrz_first or
        (extracted["Middle_name_ru"] != mrz_mid and (extracted["Middle_name_ru"] or mrz_mid))):
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Грамматический, лексический и синтаксический фильтр
    susp_org, _ = is_suspicious_org(extracted["Issue_organization_ru"])
    if susp_org:
        return {"doc_id": doc_id, "decision": "reject"}
        
    susp_bp, _ = is_suspicious_bp(extracted["Birth_place_ru"])
    if susp_bp:
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Проверка порогов уверенности OCR
    all_confs = []
    for fld in FIELDS:
        all_confs.extend(get_field_char_confs(viz.get(fld)))
        
    if not all_confs or min(all_confs) < min_conf_th:
        return {"doc_id": doc_id, "decision": "reject"}
        
    org_confs = get_field_char_confs(viz.get("Issue_organization_ru"))
    bp_confs = get_field_char_confs(viz.get("Birth_place_ru"))
    if not org_confs or min(org_confs) < min_conf_th:
        return {"doc_id": doc_id, "decision": "reject"}
    if not bp_confs or min(bp_confs) < min_conf_th:
        return {"doc_id": doc_id, "decision": "reject"}
        
    # Все проверки успешно пройдены -> принимаем!
    return {
        "doc_id": doc_id,
        "decision": "accept",
        "fields": extracted
    }


def main():
    if len(sys.argv) < 3:
        print("Использование: python postprocess.py <input_predictions.jsonl> <output_answers.jsonl>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    count_total = 0
    count_accepted = 0
    count_rejected = 0
    
    with open(input_path, "r", encoding="utf-8") as in_f, open(output_path, "w", encoding="utf-8") as out_f:
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            res = process_document(doc, min_conf_th=0.95)
            out_f.write(json.dumps(res, ensure_ascii=False) + "\n")
            count_total += 1
            if res["decision"] == "accept":
                count_accepted += 1
            else:
                count_rejected += 1
                
    print(f"Обработано документов: {count_total}")
    print(f"Принято:               {count_accepted} ({count_accepted / count_total:.1%})")
    print(f"Отклонено:             {count_rejected} ({count_rejected / count_total:.1%})")


if __name__ == "__main__":
    main()
