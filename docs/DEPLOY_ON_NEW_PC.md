# Перенос Launcher на другой компьютер (черновой режим, вручную)

## Что переносим

Код — через git из `main` (последняя версия). Данные — отдельно, см. ниже.

Брать с собой:
- весь код из репозитория (`app/`, `scripts/`, `docs/`, `tests/`, `tools/`,
  `requirements.txt`, служебные файлы);
- `runtime/manifests/` — только если буквы дисков и пути на новом ПК
  совпадают со старым; иначе объекты переимпортируются заново.

НЕ брать с собой:
- `runtime/cache/` (гигабайты, пересоздаётся сам при первом рендере);
- `runtime/logs/`, `runtime/bench/`, `runtime/dwg-probe/`;
- `__pycache__/`, `*.bak`, `*.pyc`;
- `dist/` — старые сборки.

## Требования на целевом ПК

1. **Windows 10/11**.
2. **Python 3.14** в `C:\Python314` (`python.exe` и `pythonw.exe`).
3. Зависимости Python — ставятся одной командой:
   `C:\Python314\python.exe -m pip install -r requirements.txt`
   (состав: `openpyxl`, `PyMuPDF`, `pypdf`, `pywebview`).
4. **Poppler** (`pdfinfo`, `pdftoppm`) — PDF-превью без него не работает.
   Рабочий вариант: `winget install -e --id oschwartz10612.Poppler`.
   Сервер ищет сначала `runtime/tools/poppler/Library/bin`, затем PATH.
5. **Microsoft Excel и Word** — конвертации Excel/Word в preview.
6. **ZWCAD 2025** (или AutoCAD) — рендер DWG без PDF-пар.
7. Папки объектов (Google Drive и прочие) — смонтировать как на старом ПК;
   если пути отличаются, объекты переимпортировать через кнопку «Загрузить».

## Развёртывание по шагам (для агента на новом ПК)

```powershell
# 1. Забрать код (пример пути — подставь свой):
cd C:\Users\<имя>\Documents\Codex
git clone <url-репозитория> FEngineering_Launcher_v3
cd FEngineering_Launcher_v3
git checkout main
git pull

# 2. Поставить зависимости:
C:\Python314\python.exe -m pip install -r requirements.txt

# 3. Поставить Poppler (если pdfinfo не находится):
winget install -e --id oschwartz10612.Poppler
# проверка:
Get-Command pdfinfo

# 4. Проверка синтаксиса и кодировок:
C:\Python314\python.exe -m py_compile app\backend\server.py app\flauncher.pyw
.\scripts\check_encoding.cmd

# 5. Первый запуск сервера вручную (должна появиться строка с адресом,
#    остановить через Ctrl+C после проверки):
C:\Python314\python.exe app\backend\server.py --port 8780
# в другом окне: открыть http://127.0.0.1:8780/api/health — должен ответить ok

# 6. Ярлык FLauncher на рабочий стол:
#    цель: C:\Python314\pythonw.exe
#    аргумент: "<путь>\app\flauncher.pyw"
#    рабочая папка: корень репозитория
#    иконка: app\frontend\assets\flauncher.ico
```

## Переимпорт объектов

Манифесты хранят абсолютные пути. Если диски/папки на новом ПК другие:

1. Удалить чужие манифесты из `runtime/manifests/`;
2. В лаунчере кнопкой «Загрузить» добавить корневые папки заново.

## Проверка после переноса

1. Кнопка «Загрузить» — открывается системное окно выбора папки Windows;
2. Значок открытия в дереве — открывается проводник с выделением файла;
3. Объект с PDF — страницы рендерятся и листаются;
4. `.xlsx` — табличный просмотр; `.xls`/`.doc` — конвертация через Office;
5. DWG без пары — формируется PDF-близнец и открывается как PDF;
6. Большой объект (тысячи файлов) — дерево открывается свёрнутым, без зависаний.

## Если что-то не так

- Висит чужой сервер на порту: запускалка сама гасит зависшие процессы
  нашего backend; чужой `pythonw.exe C:\...\server.py` без слушающего порта
  можно завершить вручную.
- Лог запускалки: `runtime/logs/launcher_gui.log`.
- Лог ошибок импорта: `runtime/logs/import.jsonl`.
