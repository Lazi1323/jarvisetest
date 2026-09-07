# J.A.R.V.I.S. для Nobara Linux

Локальный помощник для Linux: понимает текст и голос, видит экран, открывает приложения, ищет файлы, управляет клавиатурой и мышью, хранит память, запускает плагины и умеет работать через Groq/OpenRouter.

Инструкция рассчитана на Nobara с KDE Plasma. Для Wayland используется `ydotool`/`wtype`, для X11 — `xdotool`.

## 1. Подготовить систему

Откройте Konsole и установите системные зависимости:

```bash
sudo dnf upgrade --refresh
sudo dnf install -y \
  python3 python3-pip python3-devel python3-tkinter \
  gcc gcc-c++ make \
  xdotool ydotool wtype \
  wl-clipboard xclip \
  grim slurp spectacle scrot \
  tesseract tesseract-langpack-rus \
  mpv playerctl ripgrep fd-find \
  libsndfile alsa-utils pulseaudio-utils \
  flatpak
```

Некоторые пакеты могут быть уже установлены. Проверьте команды:

```bash
command -v python3 pip3 grim slurp tesseract mpv rg
```

Для Telegram нужен интернет и заполненные `tg_bot`/`tg_chat`. Для Flatpak:

```bash
flatpak --version
```

## 2. Скачать проект

Если проект уже открыт в VS Code, перейдите в его каталог:

```bash
cd /путь/к/проекту
```

Для клонирования репозитория:

```bash
git clone <URL_РЕПОЗИТОРИЯ> jarvis
cd jarvis
```

Проверьте файлы:

```bash
ls -la
```

В каталоге должны быть `jarvis.py`, `requirements.txt`, `config.example.json` и `plugins/`.

## 3. Создать Python-окружение

Не устанавливайте зависимости глобально:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
python -m pip install edge-tts
```

`edge-tts` нужен для русской озвучки. Проверка:

```bash
python -c "import requests, PIL, sounddevice, soundfile, vosk, pystray; print('Python-зависимости OK')"
```

В новом терминале окружение нужно активировать снова:

```bash
cd /путь/к/проекту
source .venv/bin/activate
```

## 4. Настроить API-ключи

Ключ Groq или OpenRouter нужен для ответов модели. Telegram-бот создаётся через `@BotFather`, а `tg_chat` — ID чата.

Создайте приватный конфиг:

```bash
mkdir -p ~/.config/jarvis
cp config.example.json ~/.config/jarvis/config.json
chmod 600 ~/.config/jarvis/config.json
nano ~/.config/jarvis/config.json
```

Пример структуры:

```json
{
  "groq_api_key": "gsk_НОВЫЙ_КЛЮЧ",
  "openrouter_api_key": "sk-or-v1-НОВЫЙ_КЛЮЧ",
  "tg_bot": "ТОКЕН_БОТА",
  "tg_chat": "ID_ЧАТА",
  "allow_shell_exec": false,
  "confirm_actions": true,
  "allow_screen_upload": true,
  "auto_screen": true,
  "allow_unattended_actions": false,
  "app_aliases": {
    "браузер": "firefox",
    "редактор": "code"
  }
}
```

Не вставляйте ключи из переписки или публичных сообщений: опубликованные ключи нужно отозвать и заменить. Файл `~/.config/jarvis/config.json` не добавляйте в Git.

При `allow_screen_upload: true` и `auto_screen: true` Jarvis делает снимок экрана перед запросом и отправляет его в vision-модель OpenRouter. Чтобы использовать vision только по явному запросу или полностью отключить отправку экрана, установите:

```json
"allow_screen_upload": false,
"auto_screen": false
```

Можно указать только один API-провайдер. Без ключей приложение запустится, но ответы модели работать не будут.

## 5. Настроить голосовой режим

Скачайте русскую модель Vosk с официальной страницы Vosk, распакуйте её и переименуйте каталог:

```bash
mkdir -p ~/.cache
mv ~/Downloads/vosk-model-ru-* ~/.cache/vosk-model-ru
```

Проверьте модель и микрофон:

```bash
test -f ~/.cache/vosk-model-ru/am/final.mdl && echo 'Vosk-модель OK'
arecord -l
```

Голосовое пробуждение использует слово `Джарвис`. После него говорите команду: «Джарвис, открой Firefox».

## 6. Wayland и управление мышью/клавиатурой

Проверьте тип сессии:

```bash
echo "$XDG_SESSION_TYPE"
```

Для KDE Wayland должно быть `wayland`, для X11 — `x11`.

На Wayland Jarvis использует `wtype` и `ydotool`:

```bash
command -v wtype ydotool
```

Если `ydotool` установлен, но клики не работают, запустите демон в отдельной Konsole:

```bash
sudo ydotoold
```

Оставьте его работающим и запустите Jarvis в другой вкладке. Не запускайте весь Jarvis через `sudo`: это ломает пользовательские ключи, графическую сессию и доступ к домашней директории.

Для X11 нужен `xdotool`:

```bash
command -v xdotool
```

## 7. Первый запуск

```bash
cd /путь/к/проекту
source .venv/bin/activate
python jarvis.py
```

Должно открыться окно J.A.R.V.I.S. Запускайте его из Konsole внутри Plasma, а не из SSH без X11/Wayland forwarding.

## 8. Первый тест

Выполните в окне Jarvis:

```text
/status
/plugins
/remember тестовая заметка
/find jarvis.py
```

Затем проверьте обычные запросы:

```text
Открой Firefox
Найди все файлы с именем README.md
Запомни, что я использую Nobara KDE
Что ты знаешь обо мне?
```

Опасные действия потребуют подтверждения. Кнопка `Остановить` прекращает текущую цепочку действий.

## 9. Режимы запуска

Обновить индекс приложений, плагины и модели:

```bash
python jarvis.py --reindex
```

Показать найденные модели:

```bash
python jarvis.py --models
```

Запустить фоновый режим с трей-иконкой, мониторингом и голосовым слушателем:

```bash
python jarvis.py --tray
```

Также поддерживается:

```bash
python jarvis.py --daemon
```

`--heal` используется внутренним механизмом восстановления после ошибки терминала.

## 10. Удобная команда запуска

Создайте скрипт, заменив путь на настоящий:

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/jarvis <<'EOF'
#!/usr/bin/env bash
set -e
cd /путь/к/проекту
source .venv/bin/activate
exec python jarvis.py "$@"
EOF
chmod +x ~/.local/bin/jarvis
```

Теперь доступны:

```bash
jarvis
jarvis --tray
jarvis --reindex
```

Если команда не найдена:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 11. Автозапуск в KDE

Создайте desktop-файл:

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/jarvis.desktop
```

Вставьте, заменив оба пути:

```ini
[Desktop Entry]
Type=Application
Name=J.A.R.V.I.S.
Comment=Local Linux assistant
Exec=/путь/к/проекту/.venv/bin/python /путь/к/проекту/jarvis.py --tray
Terminal=false
StartupNotify=false
X-KDE-autostart-after=panel
```

Сначала проверьте обычный запуск, затем включайте автозапуск.

## 12. Запуск GUI по `Alt+A` в KDE

GUI — это обычный режим запуска без параметров:

```bash
python jarvis.py
```

В KDE Plasma откройте:

```text
Параметры системы → Клавиатура → Сочетания клавиш → Пользовательские сочетания
```

Нажмите `Изменить → Создать → Команда или URL` и задайте:

- имя: `J.A.R.V.I.S. GUI`;
- команда: `/путь/к/проекту/.venv/bin/python /путь/к/проекту/jarvis.py`;
- сочетание: `Alt+A`.

Нажмите `Применить`, затем проверьте сочетание в любой программе. Оно должно открыть окно Jarvis.

Если хотите запускать трей-режим, укажите вместо обычного запуска:

```text
/путь/к/проекту/.venv/bin/python /путь/к/проекту/jarvis.py --tray
```

Перед добавлением сочетания обязательно проверьте команду в Konsole:

```bash
/путь/к/проекту/.venv/bin/python /путь/к/проекту/jarvis.py
```

Не используйте `sudo` в команде горячей клавиши. Если `Alt+A` уже занято KDE или другим приложением, удалите старое сочетание либо выберите свободную комбинацию.

## 13. Безопасность

По умолчанию команды `SILENT_EXEC` и `TERM_EXEC` отключены:

```json
"allow_shell_exec": false
```

Для доверенного локального режима:

```json
"allow_shell_exec": true,
"confirm_actions": true,
"allow_unattended_actions": false
```

Не включайте одновременно `allow_shell_exec: true` и `allow_unattended_actions: true` постоянно. Модель получает возможность выполнять команды от имени вашего пользователя.

Скриншоты отправляются внешнему AI-провайдеру при `allow_screen_upload: true`. Для режима «vision только по словам экран/окно» используйте:

```json
"allow_screen_upload": true,
"auto_screen": false
```

Для постоянного анализа экрана:

```json
"allow_screen_upload": true,
"auto_screen": true
```

## 14. Приложения и файлы

Jarvis умеет открывать:

- приложения из `.desktop`;
- программы из `PATH`;
- обычные исполняемые файлы и скрипты;
- AppImage;
- программы из `~/Applications`, `~/AppImages`, `~/Downloads` и `/opt`;
- команды с аргументами, например `firefox --private-window`.

Для AppImage:

```bash
chmod +x ~/Applications/MyApp.AppImage
```

Поиск файлов:

```text
/find название
/find текст внутри файла

/remind in 20m выключить музыку
/remind at 18:30 проверить почту
/tasks
```

Поиск проверяет имена и содержимое доступных текстовых файлов. Большие и бинарные файлы пропускаются.

Для ускорения используются `fd` для имён и `ripgrep` для содержимого. Можно указать режим явно:

```text
/find --name *.py
/find --content API_KEY
```

Если `fd` или `ripgrep` отсутствуют, Jarvis использует медленный Python fallback.

## 15. Плагины

Плагины можно положить в `plugins/` проекта или `~/.config/jarvis/plugins`.

Минимальный плагин:

```python
def register(api):
    api.register_action(
        "HELLO",
        "тестовое действие",
        lambda value: f"Привет, {value or 'мир'}!"
    )
```

После перезапуска проверьте:

```text
/plugins
```

Подробнее: [plugins/README.md](plugins/README.md).

В проекте уже есть плагины `TIME_NOW`, `SYSTEM_STATUS`, `MEDIA_PLAY`, `MEDIA_PAUSE`, `MEDIA_NEXT` и `MEDIA_STATUS`.

## 16. Память и файлы данных

Память хранится в SQLite и старый `memory.json` автоматически мигрируется при первом запуске.

- конфиг: `~/.config/jarvis/config.json`;
- плагины: `~/.config/jarvis/plugins`;
- память: `~/.cache/jarvis/memory.db`;
- история: `~/.cache/jarvis/history.json`;
- индекс приложений: `~/.cache/jarvis/apps_index.json`;
- кэш моделей: `~/.cache/jarvis/models_cache.json`.

Напоминания хранятся в той же базе SQLite. Планировщик работает в GUI и tray-режимах.

## 17. Частые ошибки

### `ModuleNotFoundError`

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install edge-tts
```

### `No module named tkinter`

```bash
sudo dnf install -y python3-tkinter
```

### Окно не появляется

```bash
echo "$DISPLAY"
echo "$WAYLAND_DISPLAY"
echo "$XDG_SESSION_TYPE"
```

Запускайте Jarvis из Konsole внутри Plasma.

### Не работает клик или ввод на Wayland

```bash
command -v wtype ydotool
sudo ydotoold
```

Сам Jarvis через `sudo` не запускайте.

### Не работает скриншот

```bash
command -v grim slurp spectacle scrot
```

На Wayland обычно нужны `grim` и `slurp`, на KDE также можно использовать `spectacle`.

### Не работает голос

```bash
test -f ~/.cache/vosk-model-ru/am/final.mdl
arecord -l
command -v paplay mpv edge-tts
```

### Модель не отвечает

```bash
python jarvis.py --models
```

Проверьте ключи и сеть. Никогда не публикуйте `~/.config/jarvis/config.json`.

### RAG не работает

```bash
sudo dnf install -y ripgrep
```

## 18. Проверка перед публикацией изменений

```bash
source .venv/bin/activate
python -m py_compile jarvis.py plugins/time_plugin.py
python -m json.tool config.example.json >/dev/null
python -m unittest discover -s tests -v
git diff --check
```
