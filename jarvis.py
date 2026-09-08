#!/usr/bin/env python3
import os
import sys
import time
import json
import base64
import threading
import subprocess
import requests
import re
import queue
import uuid
import struct
import math
import glob
import logging
import shutil
import tempfile
import sqlite3
import shlex
import importlib.util
import datetime as dt
import fnmatch
from io import BytesIO
from PIL import Image, ImageDraw
import tkinter as tk
from tkinter import messagebox

try:
    import sounddevice as sd
    import soundfile as sf
    from vosk import Model, KaldiRecognizer
    import wave
    AUDIO_ENABLED = True
except ImportError:
    AUDIO_ENABLED = False

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger("jarvis")

# ================= КОНФИГУРАЦИЯ =================
class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_VISION = "llama-3.2-90b-vision-preview"
    GROQ_TEXT = ["qwen/qwen3.8-27b", "qwen/qwen3.6-27b", "openai/gpt-oss-120b"]

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
    OPENROUTER_VISION_MODELS = [
        "dots-studio/dots-3-note-preview:free",
        "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    ]
    MODELS_CACHE_TTL = 3600

    TG_BOT = os.getenv("JARVIS_TG_BOT", "")
    TG_CHAT = os.getenv("JARVIS_TG_CHAT", "")
    CONFIG_DIR = os.path.expanduser("~/.config/jarvis")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
    ALLOW_SHELL_EXEC = os.getenv("JARVIS_ALLOW_SHELL_EXEC", "0").lower() in {"1", "true", "yes"}
    CONFIRM_ACTIONS = os.getenv("JARVIS_CONFIRM_ACTIONS", "1").lower() in {"1", "true", "yes"}
    ALLOW_SCREEN_UPLOAD = os.getenv("JARVIS_ALLOW_SCREEN_UPLOAD", "1").lower() in {"1", "true", "yes"}
    AUTO_SCREEN = os.getenv("JARVIS_AUTO_SCREEN", "1").lower() in {"1", "true", "yes"}
    SCREEN_CACHE_TTL = 3
    ALLOW_UNATTENDED_ACTIONS = os.getenv("JARVIS_ALLOW_UNATTENDED_ACTIONS", "0").lower() in {"1", "true", "yes"}
    MAX_HISTORY_MESSAGES = 40

    DIR_CACHE = os.path.expanduser("~/.cache/jarvis")
    FILE_HIST = os.path.join(DIR_CACHE, "history.json")
    FILE_MACRO = os.path.join(DIR_CACHE, "macros.json")
    FILE_MEM = os.path.join(DIR_CACHE, "memory.json")
    FILE_MEM_DB = os.path.join(DIR_CACHE, "memory.db")
    APP_ALIASES = {}
    APPS_INDEX = os.path.join(DIR_CACHE, "apps_index.json")
    MODELS_CACHE = os.path.join(DIR_CACHE, "models_cache.json")
    PLUGIN_DIR = os.path.join(CONFIG_DIR, "plugins")
    DIR_PROJ = os.path.expanduser("~/")

    UI_BG = "#11111b"
    UI_PANEL = "#181825"
    UI_TEXT = "#cdd6f4"
    UI_ACCENT = "#f38ba8"

    @classmethod
    def load(cls):
        os.makedirs(cls.CONFIG_DIR, exist_ok=True)
        os.makedirs(cls.DIR_CACHE, exist_ok=True)
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if "GROQ_API_KEY" not in os.environ:
                        cls.GROQ_API_KEY = cfg.get("groq_api_key", cls.GROQ_API_KEY)
                    if "OPENROUTER_API_KEY" not in os.environ:
                        cls.OPENROUTER_API_KEY = cfg.get("openrouter_api_key", cls.OPENROUTER_API_KEY)
                    if "JARVIS_TG_BOT" not in os.environ:
                        cls.TG_BOT = cfg.get("tg_bot", cls.TG_BOT)
                    if "JARVIS_TG_CHAT" not in os.environ:
                        cls.TG_CHAT = cfg.get("tg_chat", cls.TG_CHAT)
                    if "allow_shell_exec" in cfg and "JARVIS_ALLOW_SHELL_EXEC" not in os.environ:
                        cls.ALLOW_SHELL_EXEC = bool(cfg["allow_shell_exec"])
                    if "confirm_actions" in cfg and "JARVIS_CONFIRM_ACTIONS" not in os.environ:
                        cls.CONFIRM_ACTIONS = bool(cfg["confirm_actions"])
                    if "allow_screen_upload" in cfg and "JARVIS_ALLOW_SCREEN_UPLOAD" not in os.environ:
                        cls.ALLOW_SCREEN_UPLOAD = bool(cfg["allow_screen_upload"])
                    if "auto_screen" in cfg and "JARVIS_AUTO_SCREEN" not in os.environ:
                        cls.AUTO_SCREEN = bool(cfg["auto_screen"])
                    if "allow_unattended_actions" in cfg and "JARVIS_ALLOW_UNATTENDED_ACTIONS" not in os.environ:
                        cls.ALLOW_UNATTENDED_ACTIONS = bool(cfg["allow_unattended_actions"])
                    if isinstance(cfg.get("app_aliases"), dict):
                        cls.APP_ALIASES = {str(k).lower(): str(v) for k, v in cfg["app_aliases"].items()}
            except Exception as e:
                LOGGER.error("Ошибка чтения конфига: %s", e)

Config.load()

# ================= СИСТЕМА ВВОДА (WAYLAND & X11) =================
class InputDriver:
    """Универсальный драйвер эмуляции устройств ввода для Wayland (KDE KWin) и X11."""
    IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"

    @classmethod
    def mouse_click(cls, x, y, btn=1, double=False):
        btn_map = {1: "0xC0", 2: "0xC1", 3: "0xC2"} # ydotool left, right, middle flags
        if cls.IS_WAYLAND and shutil.which("ydotool"):
            subprocess.run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            click_args = ["ydotool", "click", btn_map.get(btn, "0xC0")]
            subprocess.Popen(click_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if double:
                subprocess.Popen(click_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            btn_flag = 1 if btn == 1 else (3 if btn == 3 else 2)
            args = ["xdotool", "mousemove", str(x), str(y), "click"]
            args += ["--repeat", "2", "--delay", "100", str(btn_flag)] if double else [str(btn_flag)]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def mouse_scroll(cls, direction):
        if "up" in str(direction).lower():
            args = ["ydotool", "mousemove", "-w", "--", "0", "1"] if cls.IS_WAYLAND else ["xdotool", "click", "4"]
        else:
            args = ["ydotool", "mousemove", "-w", "--", "0", "-1"] if cls.IS_WAYLAND else ["xdotool", "click", "5"]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def press_key(cls, keys):
        k = keys.strip()
        if cls.IS_WAYLAND:
            if k.lower() == "super":
                if shutil.which("wtype"):
                    subprocess.Popen(["wtype", "-k", "Super_L"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif shutil.which("ydotool"):
                    subprocess.Popen(["ydotool", "key", "125:1", "125:0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                command = ["wtype", "-k", k] if shutil.which("wtype") else ["xdotool", "key", "--clearmodifiers", k]
                subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            key_name = "Super_L" if k.lower() == "super" else k
            subprocess.Popen(["xdotool", "key", "--clearmodifiers", key_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def type_text(cls, text):
        time.sleep(0.05)
        if cls.IS_WAYLAND:
            command = ["wtype", text] if shutil.which("wtype") else ["ydotool", "type", text]
        else:
            command = ["xdotool", "type", "--clearmodifiers", text]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ================= АВТОПОДБОР МОДЕЛЕЙ =================
class OpenRouterManager:
    _cache = {"models": None, "timestamp": 0}

    @classmethod
    def get_models(cls, force_refresh=False):
        now = time.time()
        if not force_refresh and cls._cache["models"] and (now - cls._cache["timestamp"] < Config.MODELS_CACHE_TTL):
            return cls._cache["models"]

        try:
            if os.path.exists(Config.MODELS_CACHE) and not force_refresh:
                if now - os.path.getmtime(Config.MODELS_CACHE) < Config.MODELS_CACHE_TTL:
                    with open(Config.MODELS_CACHE, "r", encoding="utf-8") as f:
                        cls._cache["models"] = json.load(f)
                        cls._cache["timestamp"] = now
                        return cls._cache["models"]
        except Exception:
            pass

        models = {"free_vision": [], "free_text": [], "paid_vision": [], "paid_text": []}
        if Config.OPENROUTER_API_KEY:
            try:
                r = requests.get(
                    Config.OPENROUTER_MODELS_URL,
                    headers={"Authorization": f"Bearer {Config.OPENROUTER_API_KEY}"},
                    timeout=15
                )
                if r.status_code == 200:
                    data = r.json().get("data", [])
                    for m in data:
                        mid = m.get("id", "")
                        is_free = mid.endswith(":free") or str(m.get("pricing", {}).get("prompt", "0")) == "0"
                        arch = m.get("architecture", {})
                        supports_vision = "image" in arch.get("input_modalities", []) or "image" in str(arch).lower()
                        entry = {"id": mid, "name": m.get("name", mid), "vision": supports_vision}

                        if is_free:
                            if supports_vision:
                                models["free_vision"].append(entry)
                            else:
                                models["free_text"].append(entry)
                        else:
                            if supports_vision:
                                models["paid_vision"].append(entry)
                            else:
                                models["paid_text"].append(entry)

                    models["free_vision"].sort(key=lambda x: "90b" in x["id"] or "70b" in x["id"], reverse=True)
                    models["free_text"].sort(key=lambda x: "70b" in x["id"] or "72b" in x["id"] or "27b" in x["id"], reverse=True)
            except Exception:
                pass

        if not models["free_text"]:
            models["free_text"] = [
                {"id": "meta-llama/llama-3.3-70b-instruct:free", "vision": False},
                {"id": "qwen/qwen-2.5-72b-instruct:free", "vision": False},
                {"id": "deepseek/deepseek-chat-v3-0324:free", "vision": False}
            ]
        if not models["free_vision"]:
            models["free_vision"] = [
                {"id": "google/gemini-2.0-flash-exp:free", "vision": True},
                {"id": "meta-llama/llama-3.2-90b-vision-preview:free", "vision": True}
            ]

        cls._cache["models"] = models
        cls._cache["timestamp"] = now
        try:
            with open(Config.MODELS_CACHE, "w", encoding="utf-8") as f:
                json.dump(models, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return models

# ================= ПАМЯТЬ =================
class MemoryManager:
    @staticmethod
    def _load(file_path, default):
        try:
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    @staticmethod
    def _save(file_path, data):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=".jarvis-", dir=os.path.dirname(file_path), text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception as e:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
            LOGGER.error("Ошибка сохранения %s: %s", file_path, e)

    @classmethod
    def _db(cls):
        os.makedirs(os.path.dirname(Config.FILE_MEM_DB), exist_ok=True)
        conn = sqlite3.connect(Config.FILE_MEM_DB)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS memories ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL UNIQUE, "
            "category TEXT NOT NULL DEFAULT 'fact', created_at REAL NOT NULL)"
        )
        try:
            conn.execute("ALTER TABLE memories ADD COLUMN category TEXT NOT NULL DEFAULT 'fact'")
        except sqlite3.OperationalError:
            pass
        if os.path.exists(Config.FILE_MEM) and conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0:
            legacy = cls._load(Config.FILE_MEM, [])
            conn.executemany(
                "INSERT OR IGNORE INTO memories(text, category, created_at) VALUES (?, ?, ?)",
                [(str(item), "fact", time.time()) for item in legacy if str(item).strip()]
            )
            conn.commit()
        return conn

    @classmethod
    def save_macro(cls, name, x, y):
        m = cls._load(Config.FILE_MACRO, {})
        m[name.lower()] = {"x": x, "y": y}
        cls._save(Config.FILE_MACRO, m)

    @classmethod
    def get_macro(cls, name):
        return cls._load(Config.FILE_MACRO, {}).get(name.lower())

    @classmethod
    def save_memory(cls, text, category="fact"):
        text = text.strip()
        if not text:
            return
        conn = cls._db()
        conn.execute("INSERT OR IGNORE INTO memories(text, category, created_at) VALUES (?, ?, ?)", (text, category, time.time()))
        conn.execute(
            "DELETE FROM memories WHERE id NOT IN (SELECT id FROM memories ORDER BY id DESC LIMIT 100)"
        )
        conn.commit()
        conn.close()

    @classmethod
    def forget_memory(cls, text):
        needle = text.strip().lower()
        if not needle:
            return 0
        conn = cls._db()
        cursor = conn.execute("DELETE FROM memories WHERE lower(text) LIKE ?", (f"%{needle}%",))
        conn.commit()
        removed = cursor.rowcount
        conn.close()
        return removed

    @classmethod
    def get_memory_context(cls):
        conn = cls._db()
        mem = [f"[{row[1]}] {row[0]}" for row in conn.execute("SELECT text, category FROM memories ORDER BY id DESC LIMIT 40")]
        conn.close()
        return "\n".join(f"- {m}" for m in mem) if mem else "Пока пусто."

    @classmethod
    def schedule_task(cls, title, due_at, repeat_seconds=None):
        conn = cls._db()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, due_at REAL NOT NULL, repeat_seconds REAL, done INTEGER NOT NULL DEFAULT 0)"
        )
        cursor = conn.execute(
            "INSERT INTO tasks(title, due_at, repeat_seconds) VALUES (?, ?, ?)",
            (title.strip(), float(due_at), repeat_seconds)
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        return task_id

    @classmethod
    def list_tasks(cls, include_done=False):
        conn = cls._db()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, due_at REAL NOT NULL, repeat_seconds REAL, done INTEGER NOT NULL DEFAULT 0)"
        )
        query = "SELECT id, title, due_at, done FROM tasks " + ("ORDER BY due_at" if include_done else "WHERE done = 0 ORDER BY due_at")
        rows = conn.execute(query).fetchall()
        conn.close()
        return rows

    @classmethod
    def take_due_tasks(cls, now=None):
        now = now or time.time()
        conn = cls._db()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, due_at REAL NOT NULL, repeat_seconds REAL, done INTEGER NOT NULL DEFAULT 0)"
        )
        rows = conn.execute("SELECT id, title, repeat_seconds FROM tasks WHERE done = 0 AND due_at <= ?", (now,)).fetchall()
        for task_id, _, repeat_seconds in rows:
            if repeat_seconds:
                conn.execute("UPDATE tasks SET due_at = ?, done = 0 WHERE id = ?", (now + repeat_seconds, task_id))
            else:
                conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        return [(task_id, title) for task_id, title, _ in rows]


class TaskScheduler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="jarvis-scheduler")
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.wait(5):
            for _, title in MemoryManager.take_due_tasks():
                LOGGER.info("Напоминание: %s", title)
                SystemCore.notify(f"⏰ {title}", 10000)
                AudioEngine.speak(f"Напоминание. {title}")

# ================= ЛОКАЛЬНЫЕ ИНСТРУМЕНТЫ =================
class FileSearch:
    ROOTS = [
        os.path.expanduser("~"),
        "/opt",
        "/usr/local/bin",
        "/usr/share/applications"
    ]
    SKIP_DIRS = {".cache", ".git", "node_modules", "__pycache__", ".venv", "venv"}

    @classmethod
    def search(cls, query, roots=None, limit=40, mode="auto"):
        query = query.strip()
        if not query:
            return []
        if query.startswith("--name "):
            mode, query = "name", query[7:].strip()
        elif query.startswith("--content "):
            mode, query = "content", query[10:].strip()
        needle = query.lower()
        roots = roots or cls.ROOTS
        if mode in {"auto", "name"} and shutil.which("fd"):
            pattern = query if any(char in query for char in "*?[") else f"*{query}*"
            args = ["fd", "--type", "f", "--hidden", "--follow", "--glob", pattern, "--max-results", str(limit)]
            for skip in cls.SKIP_DIRS:
                args.extend(["--exclude", skip])
            args.append("--")
            args.extend(roots)
            try:
                output = subprocess.run(args, capture_output=True, text=True, check=False).stdout
                name_results = [(line, "имя файла") for line in output.splitlines()[:limit]]
                if mode == "name" or name_results:
                    if mode == "name":
                        return name_results
                else:
                    name_results = []
            except OSError:
                name_results = []
        else:
            name_results = []

        if mode in {"auto", "content"} and shutil.which("rg"):
            args = ["rg", "--files-with-matches", "--hidden", "--ignore-case", "-m", "1"]
            for skip in cls.SKIP_DIRS:
                args.extend(["--glob", f"!{skip}/**"])
            args.extend(["--", query])
            args.extend(roots)
            try:
                output = subprocess.run(args, capture_output=True, text=True, check=False).stdout
                content_results = [(line, "содержимое") for line in output.splitlines()[:limit]]
                if mode == "content" or content_results:
                    return name_results[:limit] + content_results[:max(0, limit - len(name_results))]
            except OSError:
                pass

        results = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            for current, dirs, files in os.walk(root, topdown=True, onerror=lambda _: None):
                dirs[:] = [d for d in dirs if d not in cls.SKIP_DIRS and not d.startswith("/proc")]
                for filename in files:
                    path = os.path.join(current, filename)
                    if mode != "content" and (needle in filename.lower() or fnmatch.fnmatch(filename.lower(), needle)):
                        results.append((path, "имя файла"))
                    elif mode != "name" and len(results) < limit and cls._contains(path, needle):
                        results.append((path, "содержимое"))
                    if len(results) >= limit:
                        return results
        return results

    @staticmethod
    def _contains(path, needle):
        try:
            if os.path.getsize(path) > 2 * 1024 * 1024:
                return False
            with open(path, "r", encoding="utf-8", errors="ignore") as stream:
                return needle in stream.read().lower()
        except (OSError, UnicodeError):
            return False

    @classmethod
    def format_results(cls, query):
        results = cls.search(query)
        if not results:
            return f"По запросу «{query}» ничего не найдено."
        lines = [f"Найдено по запросу «{query}»: "]
        lines.extend(f"- {path} ({kind})" for path, kind in results)
        return "\n".join(lines)


class PluginManager:
    actions = {}
    modules = []

    @classmethod
    def register_action(cls, name, description, handler):
        cls.actions[name.upper()] = {"description": description, "handler": handler}

    @classmethod
    def load(cls):
        plugin_dirs = [Config.PLUGIN_DIR, os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")]
        os.makedirs(Config.PLUGIN_DIR, exist_ok=True)
        cls.actions.clear()
        cls.modules.clear()
        plugin_paths = []
        for plugin_dir in plugin_dirs:
            plugin_paths.extend(glob.glob(os.path.join(plugin_dir, "*.py")))
        for path in plugin_paths:
            try:
                module_name = f"jarvis_plugin_{uuid.uuid4().hex}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register = getattr(module, "register", None)
                if callable(register):
                    register(cls)
                    cls.modules.append(os.path.basename(path))
            except Exception as exc:
                LOGGER.warning("Не удалось загрузить плагин %s: %s", path, exc)

    @classmethod
    def execute(cls, name, value):
        action = cls.actions.get(name.upper())
        if not action:
            return f"Плагин {name} не найден."
        try:
            return str(action["handler"](value))
        except Exception as exc:
            LOGGER.exception("Ошибка плагина %s", name)
            return f"Ошибка плагина {name}: {exc}"

    @classmethod
    def prompt_context(cls):
        if not cls.actions:
            return "Плагины: нет загруженных действий."
        items = ", ".join(f"{name} ({item['description']})" for name, item in cls.actions.items())
        return f"Плагины: {items}"

# ================= СИСТЕМНЫЙ СКАНЕР =================
PluginManager.load()

class SystemScanner:
    ALIASES = {
        "дискорд": ["discord", "vesktop", "webcord"],
        "discord": ["discord", "vesktop"],
        "код": ["code", "visual-studio-code"],
        "vscode": ["code", "visual-studio-code"],
        "майнкрафт": ["prismlauncher", "tlauncher", "minecraft"],
        "стим": ["steam"],
        "steam": ["steam"],
        "браузер": ["google-chrome", "firefox", "brave-browser", "chromium"],
        "телеграм": ["telegram-desktop"],
        "терминал": ["konsole", "ptyxis", "gnome-terminal", "alacritty", "kitty"]
    }

    @classmethod
    def build_full_index(cls):
        app_map = {}
        dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications")
        ]
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for desktop_path in glob.glob(os.path.join(d, "**/*.desktop"), recursive=True):
                try:
                    name, exec_cmd, keywords, nodisplay = "", "", "", False
                    with open(desktop_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            l = line.strip()
                            if l.startswith("Name=") and not name:
                                name = l[5:]
                            elif l.startswith("Exec=") and not exec_cmd:
                                exec_cmd = l[5:]
                            elif l.startswith("Keywords=") and not keywords:
                                keywords = l[9:].replace(";", " ")
                            elif l == "NoDisplay=true":
                                nodisplay = True
                    if nodisplay or not name or not exec_cmd:
                        continue
                    file_id = os.path.basename(desktop_path).replace(".desktop", "").lower()
                    clean_exec = re.sub(r'%[a-zA-Z0-9]', '', exec_cmd).strip()
                    entry = {"name": name, "exec": clean_exec, "desktop": desktop_path, "id": file_id, "keywords": keywords}
                    app_map[name.lower()] = entry
                    app_map[file_id] = entry
                    for keyword in keywords.lower().split():
                        if keyword and keyword not in app_map:
                            app_map[keyword] = entry
                    bin_first = clean_exec.split()[0].split("/")[-1].lower()
                    if bin_first not in app_map:
                        app_map[bin_first] = entry
                except Exception:
                    continue
        MemoryManager._save(Config.APPS_INDEX, app_map)
        return app_map

    @classmethod
    def resolve_app(cls, target):
        index = cls.build_full_index() if not os.path.exists(Config.APPS_INDEX) else MemoryManager._load(Config.APPS_INDEX, {})
        t_clean = target.lower().strip()
        t_clean = Config.APP_ALIASES.get(t_clean, t_clean)
        expanded = os.path.expanduser(target.strip())
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return shlex.join([expanded])
        try:
            parts = shlex.split(target)
            if parts:
                executable = os.path.expanduser(parts[0])
                if os.path.isfile(executable) and os.access(executable, os.X_OK):
                    return shlex.join([executable] + parts[1:])
        except ValueError:
            parts = []
        command_name = os.path.basename(parts[0]).lower() if parts else t_clean.split()[0]
        candidates = [t_clean, command_name] + cls.ALIASES.get(command_name, []) + cls.ALIASES.get(t_clean, [])
        for cand in candidates:
            for key, app in index.items():
                if cand == key or cand in key:
                    return f"gio launch '{app['desktop']}'" if os.path.exists(app["desktop"]) else app["exec"]
            if shutil.which(cand):
                return cand
        for base in [os.path.expanduser("~/Applications"), os.path.expanduser("~/AppImages"), os.path.expanduser("~/Downloads"), "/opt"]:
            if not os.path.isdir(base):
                continue
            for current, _, files in os.walk(base):
                for filename in files:
                    candidate = os.path.join(current, filename)
                    if t_clean in filename.lower() and os.access(candidate, os.X_OK):
                        return shlex.join([candidate])
        flat_check = subprocess.run(
            ["flatpak", "list", "--columns=application"],
            capture_output=True,
            text=True,
            check=False
        )
        for app_id in flat_check.stdout.splitlines():
            if t_clean in app_id.lower():
                return f"flatpak run {app_id.strip()}"
        return target

    @classmethod
    def get_system_prompt_context(cls):
        index = MemoryManager._load(Config.APPS_INDEX, {})
        if not index:
            index = cls.build_full_index()
        return "Установленный софт: " + ", ".join(sorted(list(set(v["name"] for v in index.values())))[:60]) + "\n" + PluginManager.prompt_context()

# ================= ЯДРО СИСТЕМЫ =================
class SystemCore:
    EN_CHARS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./~QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?"
    RU_CHARS = "ёйцукенгшщзхъфывапролджэячсмитьбю.ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"
    T_EN_RU = str.maketrans(EN_CHARS, RU_CHARS)
    T_RU_EN = str.maketrans(RU_CHARS, EN_CHARS)
    _screen_cache = {"value": None, "timestamp": 0}

    @staticmethod
    def get_screen_size():
        # Поддержка Wayland kscreen-doctor / wlr-randr
        try:
            out = subprocess.run("kscreen-doctor -o 2>/dev/null", shell=True, capture_output=True, text=True).stdout
            m = re.search(r'Geometry:\s*\d+,\d+\s+(\d+)x(\d+)', out)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        try:
            out = subprocess.run("xdotool getdisplaygeometry 2>/dev/null", shell=True, capture_output=True, text=True).stdout.strip()
            if out:
                w, h = out.split()
                return int(w), int(h)
        except Exception:
            pass
        return 1920, 1080

    @staticmethod
    def get_active_window_title():
        # Wayland (KDE KWin scripting через kdotool) / X11
        cmd = "kdotool getactivewindow getwindowname 2>/dev/null || xdotool getactivewindow getwindowname 2>/dev/null"
        title = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()
        return title if title else "Рабочий стол"

    @staticmethod
    def get_env():
        env = os.environ.copy()
        env["PATH"] = ":".join(["/usr/bin", "/usr/local/bin", "/var/lib/flatpak/exports/bin", os.path.expanduser("~/.local/bin")]) + ":" + env.get("PATH", "")
        return env

    @staticmethod
    def notify(msg, t=2500):
        subprocess.Popen(["notify-send", "Jarvis", str(msg), "-t", str(t), "-u", "normal"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def media_duck(duck=True):
        subprocess.Popen(f"playerctl volume {'0.15' if duck else '1.0'} 2>/dev/null", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def tg_send(text):
        if Config.TG_BOT and Config.TG_CHAT:
            threading.Thread(
                target=lambda: requests.get(
                    f"https://api.telegram.org/bot{Config.TG_BOT}/sendMessage",
                    params={"chat_id": Config.TG_CHAT, "text": text},
                    timeout=5
                ),
                daemon=True
            ).start()

    @staticmethod
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, shell=isinstance(cmd, str)).stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def get_clipboard(primary=False):
        c1 = "wl-paste -p --no-newline" if primary else "wl-paste --no-newline"
        c2 = "xclip -o -selection primary" if primary else "xclip -o -selection clipboard"
        return SystemCore.run(f"{c1} 2>/dev/null") or SystemCore.run(f"{c2} 2>/dev/null")

    @staticmethod
    def copy_to_clipboard(text):
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
        except Exception:
            subprocess.Popen(f"xclip -selection clipboard", stdin=subprocess.PIPE, shell=True, text=True).communicate(input=text)

    @staticmethod
    def window_control(action):
        act = action.lower().strip()
        if act == "close":
            subprocess.Popen("kdotool getactivewindow windowclose 2>/dev/null || xdotool getactivewindow windowclose 2>/dev/null || wtype -M alt -k F4 -m alt", shell=True)
        elif act == "minimize":
            subprocess.Popen("kdotool getactivewindow windowminimize 2>/dev/null || xdotool getactivewindow windowminimize 2>/dev/null", shell=True)
        elif act in ["maximize", "fullscreen"]:
            InputDriver.press_key("F11")
        elif act == "next":
            subprocess.Popen("wtype -M alt -k Tab -m alt 2>/dev/null || xdotool key Alt+Tab", shell=True)

    @classmethod
    def fix_layout(cls):
        txt = cls.get_clipboard(primary=True) or cls.get_clipboard(primary=False)
        if not txt:
            return
        ru_cnt = sum(1 for c in txt if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
        en_cnt = sum(1 for c in txt if 'a' <= c.lower() <= 'z')
        fixed = txt.translate(cls.T_EN_RU) if en_cnt >= ru_cnt else txt.translate(cls.T_RU_EN)
        if fixed and fixed != txt:
            time.sleep(0.05)
            InputDriver.press_key("BackSpace")
            InputDriver.type_text(fixed)

    @staticmethod
    def capture_screen():
        now = time.time()
        if SystemCore._screen_cache["value"] and now - SystemCore._screen_cache["timestamp"] < Config.SCREEN_CACHE_TTL:
            return SystemCore._screen_cache["value"]
        tmp = f"/tmp/j_snap_{uuid.uuid4().hex[:6]}.png"
        cmd = f"grim {tmp} 2>/dev/null || spectacle -b -n -o {tmp} 2>/dev/null || scrot {tmp} 2>/dev/null"
        if subprocess.Popen(cmd, shell=True).wait() == 0 and os.path.exists(tmp):
            try:
                with Image.open(tmp) as img:
                    img.thumbnail((1920, 1080))
                    buf = BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                os.remove(tmp)
                encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
                SystemCore._screen_cache = {"value": encoded, "timestamp": now}
                return encoded
            except Exception:
                pass
        return None

    @classmethod
    def launch(cls, target_cmd, is_silent=True, gui_instance=None):
        final_cmd = SystemScanner.resolve_app(target_cmd)
        env = cls.get_env()
        if is_silent:
            subprocess.Popen(final_cmd, shell=True, env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return

        # Безопасная эскалация прав через pkexec / kdesu
        if final_cmd.strip().startswith("sudo "):
            core_subcmd = final_cmd.strip()[5:].strip()
            final_cmd = f"pkexec {core_subcmd}"

        if gui_instance:
            gui_instance.root.after(0, lambda: gui_instance.out.insert(tk.END, f"\n⚙️ Терминал:\n$ {final_cmd}\n"))
            gui_instance.root.after(0, gui_instance.out.see, tk.END)

        sp = f"/tmp/j_run_{uuid.uuid4().hex[:6]}.sh"
        safe_cmd = final_cmd.replace("'", "'\\''")
        with open(sp, "w", encoding="utf-8") as f:
            f.write(
                f"#!/bin/bash\n"
                f"echo '🚀 {safe_cmd}'\n"
                f"echo '--------------------------------'\n"
                f"{final_cmd} 2> /tmp/j_heal.log\n"
                f"EC=$?\n"
                f"echo '--------------------------------'\n"
                f"if [ $EC -ne 0 ]; then cp /tmp/j_heal.log /tmp/j_heal; echo '❌ Код ошибки: '$EC; else echo '✅ Успешно выполнено'; fi\n"
                f"echo '\n[Нажми Enter для закрытия]'; read\n"
                f"rm -f '{sp}'\n"
            )
        os.chmod(sp, 0o755)
        for term in [f"konsole --hold -e bash '{sp}'", f"gnome-terminal -- bash '{sp}'", f"ptyxis -- bash '{sp}'", f"alacritty -e bash '{sp}'"]:
            if cls.run(f"which {term.split()[0]}"):
                subprocess.Popen(term, shell=True, env=env, stderr=subprocess.DEVNULL)
                break

# ================= АУДИО =================
class AudioEngine(threading.Thread):
    def __init__(self, ai_provider):
        super().__init__(daemon=True)
        self.ai = ai_provider
        self.q = queue.Queue()
        self.mp = os.path.expanduser("~/.cache/vosk-model-ru")
        self.silence_threshold = 300
        self.silence_duration = 0.8
        self.listening = False

    def _audio_cb(self, indata, frames, time_info, status):
        self.q.put(bytes(indata))

    def _get_rms(self, data):
        cnt = len(data) // 2
        if cnt == 0:
            return 0
        shorts = struct.unpack(f"<{cnt}h", data)
        return math.sqrt(sum(s * s for s in shorts) / cnt)

    @staticmethod
    def speak(text):
        subprocess.run(["pkill", "-f", "mpv.*jarvis-"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        time.sleep(0.05)
        clean = re.sub(r'```.*?```', 'информация на экране', text, flags=re.DOTALL)
        clean = re.sub(r'[*#_`"\']', '', clean).replace('\n', ' ').strip()
        if len(clean) < 2:
            return
        e = os.path.expanduser("~/.local/bin/edge-tts") if os.path.exists(os.path.expanduser("~/.local/bin/edge-tts")) else "edge-tts"
        media_path = os.path.join(tempfile.gettempdir(), f"jarvis-{uuid.uuid4().hex}.mp3")

        def _speak_thread():
            try:
                tts = subprocess.run(
                    [e, "--voice", "ru-RU-DmitryNeural", "--rate=+12%", "--text", clean, "--write-media", media_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if tts.returncode == 0:
                    subprocess.run(["mpv", "--no-video", "--volume=100", media_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except OSError as exc:
                LOGGER.warning("Озвучка недоступна: %s", exc)
            finally:
                SystemCore.media_duck(False)
                try:
                    os.remove(media_path)
                except FileNotFoundError:
                    pass

        threading.Thread(target=_speak_thread, daemon=True).start()

    def run(self):
        if not AUDIO_ENABLED or not os.path.exists(self.mp):
            LOGGER.warning("Голосовой режим отключён: нет аудиозависимостей или модели Vosk (%s)", self.mp)
            return
        try:
            model = Model(self.mp)
            rec = KaldiRecognizer(model, 16000)
        except Exception as e:
            LOGGER.exception("Ошибка инициализации Vosk: %s", e)
            return

        while True:
            try:
                with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16', channels=1, callback=self._audio_cb):
                    self.listening = True
                    while True:
                        try:
                            data_chunk = self.q.get(timeout=2)
                        except queue.Empty:
                            continue
                        if rec.AcceptWaveform(data_chunk):
                            res = json.loads(rec.Result())
                            if "джарвис" in res.get("text", "").lower():
                                self._handle_wake_word()
            except Exception as exc:
                self.listening = False
                SystemCore.media_duck(False)
                LOGGER.exception("Аудиопоток перезапущен после ошибки: %s", exc)
                time.sleep(3)

    def _handle_wake_word(self):
        SystemCore.media_duck(True)
        try:
            SystemCore.notify("🎙️ Слушаю...", 2000)
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"], stderr=subprocess.DEVNULL)
            with self.q.mutex:
                self.q.queue.clear()
            data = bytearray()
            silence_frames = 0
            frames_needed = int(16000 * self.silence_duration / 4000)
            started = time.monotonic()
            while time.monotonic() - started < 12:
                try:
                    chunk = self.q.get(timeout=1)
                except queue.Empty:
                    continue
                data.extend(chunk)
                if self._get_rms(chunk) < self.silence_threshold:
                    silence_frames += 1
                else:
                    silence_frames = 0
                if silence_frames >= frames_needed and len(data) > 16000 * 2 * 0.5:
                    break

            if len(data) < 16000 * 2 * 0.5:
                SystemCore.notify("❌ Не услышал команду", 2000)
                return

            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], stderr=subprocess.DEVNULL)
            SystemCore.notify("⏳ Думаю...", 2000)
            rp = os.path.join(tempfile.gettempdir(), f"jarvis-command-{uuid.uuid4().hex}.wav")
            try:
                with wave.open(rp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(data)
                txt = ""
                if Config.GROQ_API_KEY:
                    with open(rp, "rb") as af:
                        response = requests.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"},
                            files={"file": (rp, af, "audio/wav")},
                            data={"model": "whisper-large-v3", "language": "ru"},
                            timeout=10
                        )
                    if response.status_code == 200:
                        txt = response.json().get("text", "").strip()
                if txt:
                    txt = re.sub(r'^[мМэЭаА][,\s]+', '', txt).strip()
                    SystemCore.notify(f"🧠 {txt}", 4000)
                    self.ai.process_voice_command(txt)
                else:
                    SystemCore.notify("❌ Не распознано или не настроен GROQ_API_KEY", 2500)
            finally:
                try:
                    os.remove(rp)
                except FileNotFoundError:
                    pass
        except Exception as exc:
            LOGGER.exception("Ошибка обработки голосовой команды: %s", exc)
            SystemCore.notify("❌ Ошибка голосовой команды. Слушатель продолжит работу.", 3000)
        finally:
            SystemCore.media_duck(False)

# ================= ИИ ПРОВАЙДЕР =================
class AIProvider:
    @staticmethod
    def _clean(text):
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    def _call_api(self, url, key, model, payload):
        if not key:
            return None
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        if "openrouter" in url:
            headers["HTTP-Referer"] = "https://github.com/jarvis"
            headers["X-Title"] = "Jarvis"
        for attempt in range(2):
            try:
                r = requests.post(
                    url,
                    json={
                        "model": model,
                        "messages": payload,
                        "temperature": 0.2,
                        "max_tokens": 1500
                    },
                    headers=headers,
                    timeout=18
                )
                if r.status_code == 200:
                    return self._clean(r.json()["choices"][0]["message"]["content"])
                LOGGER.warning("Провайдер вернул HTTP %s для модели %s", r.status_code, model)
                if r.status_code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.warning("Некорректный ответ провайдера %s: %s", model, exc)
                break
            except requests.RequestException as exc:
                LOGGER.warning("Ошибка сети для модели %s: %s", model, exc)
            if attempt == 0:
                time.sleep(0.7)
        return None

    def ask(self, messages, screen_b64, meta):
        apps_summary = SystemScanner.get_system_prompt_context()
        w, h = SystemCore.get_screen_size()

        sys_p = (
            f"Ты J.A.R.V.I.S. — автономный агент управления ПК под Linux (KDE Wayland/X11). Разрешение экрана: {w}x{h}.\n"
            f"{apps_summary}\n"
            f"ДОЛГОСРОЧНАЯ ПАМЯТЬ:\n{MemoryManager.get_memory_context()}\n"
            "СТРОГИЕ ПРАВИЛА ВЫПОЛНЕНИЯ:\n"
            "1. Не отвечай односложно. Давай четкий, осмысленный ответ на русском языке.\n"
            f"2. Для взаимодействия с элементами экрана вычисляй координаты (X от 0 до {w}, Y от 0 до {h}).\n"
            "3. Команды управления размещай СТРОГО В САМОМ КОНЦЕ ответа, каждую с новой строки.\n"
            "ФОРМАТ КОМАНД:\n"
            "CLICK: <x>, <y>\n"
            "DCLICK: <x>, <y>\n"
            "RCLICK: <x>, <y>\n"
            "KEY: <hotkey>\n"
            "TYPE: <текст>\n"
            "SCROLL: <up/down>\n"
            "WINDOW: <close/minimize/maximize/next>\n"
            "SILENT_EXEC: <команда терминала без окна>\n"
            "TERM_EXEC: <команда терминала в отдельном окне>\n"
            "TG_SEND: <сообщение>\n"
            "MEMORY_SAVE: <сохраняемый факт>\n"
            "SEARCH_FILES: <имя или текст для поиска по файлам>\n"
            "PLUGIN: <ИМЯ> | <аргументы>\n"
            "Если передано изображение экрана, анализируй только реально видимые элементы и не выдумывай координаты.\n"
        )

        clean_history = [m for m in messages[:-1] if isinstance(m.get("content", ""), str) and len(m.get("content", "").strip()) > 1]
        clean_history = clean_history[-Config.MAX_HISTORY_MESSAGES:]
        last_prompt = messages[-1]["content"] if messages else ""
        combined = f"[АКТИВНОЕ ОКНО]: {meta}\n[ЗАПРОС]: {last_prompt}"
        user_content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screen_b64}"}}, {"type": "text", "text": combined}] if screen_b64 else combined
        payload = [{"role": "system", "content": sys_p}] + clean_history + [{"role": "user", "content": user_content}]

        raw = None
        need_vision = screen_b64 is not None

        # 1. OpenRouter (Free)
        models = OpenRouterManager.get_models()
        if need_vision:
            preferred = [{"id": model_id, "vision": True} for model_id in Config.OPENROUTER_VISION_MODELS]
            preferred_ids = {item["id"] for item in preferred}
            candidates = preferred + [
                item for item in models.get("free_vision", [])
                if isinstance(item, dict) and item.get("id") not in preferred_ids
            ]
        else:
            candidates = models.get("free_text", [])
        for m in candidates[:2]:
            mid = m["id"] if isinstance(m, dict) else m
            supports_vision = isinstance(m, dict) and m.get("vision", False)
            payload_try = [{"role": "system", "content": sys_p}] + clean_history + [{"role": "user", "content": user_content if (need_vision and supports_vision) else combined}]
            raw = self._call_api(Config.OPENROUTER_URL, Config.OPENROUTER_API_KEY, mid, payload_try)
            if raw and len(raw.strip()) > 2:
                break

        # 2. Groq Fallback
        if not raw or len(raw.strip()) <= 2:
            if need_vision:
                raw = self._call_api(Config.GROQ_URL, Config.GROQ_API_KEY, Config.GROQ_VISION, payload)
            if not raw or len(raw.strip()) <= 2:
                payload_text = [{"role": "system", "content": sys_p}] + clean_history + [{"role": "user", "content": combined}]
                for m in Config.GROQ_TEXT:
                    raw = self._call_api(Config.GROQ_URL, Config.GROQ_API_KEY, m, payload_text)
                    if raw and len(raw.strip()) > 2:
                        break

        if not raw or len(raw.strip()) <= 2:
            return "Не удалось связаться с языковыми моделями. Проверьте API-ключи и сетевое подключение, сэр.", []

        # Парсинг команд
        actions = []
        action_prefixes = ["CLICK:", "DCLICK:", "RCLICK:", "KEY:", "TYPE:", "SCROLL:", "WINDOW:", "SILENT_EXEC:", "TERM_EXEC:", "TG_SEND:", "MEMORY_SAVE:", "SEARCH_FILES:", "PLUGIN:"]
        text_lines = []
        for line in raw.splitlines():
            matched = False
            for pfx in action_prefixes:
                if line.strip().startswith(pfx):
                    val = line.strip()[len(pfx):].strip().replace("`", "")
                    actions.append((pfx.replace(":", ""), val))
                    matched = True
                    break
            if not matched:
                text_lines.append(line)

        clean_text = "\n".join(text_lines).strip()
        if not clean_text:
            clean_text = "Принято к исполнению."
        return clean_text, actions

    def process_voice_command(self, text):
        chats = MemoryManager._load(Config.FILE_HIST, [{"title": "Голос", "messages": []}])
        chats[0]["messages"].append({"role": "user", "content": text})
        needs_vision = Config.AUTO_SCREEN or any(w in text.lower() for w in ["экран", "окн", "видит", "смотри", "клик", "нажми", "где", "кнопк", "блок"])
        scr = SystemCore.capture_screen() if needs_vision and Config.ALLOW_SCREEN_UPLOAD else None
        ans, actions = self.ask(chats[0]["messages"], scr, SystemCore.get_active_window_title())
        chats[0]["messages"].append({"role": "assistant", "content": ans})
        chats[0]["messages"] = chats[0]["messages"][-Config.MAX_HISTORY_MESSAGES:]
        MemoryManager._save(Config.FILE_HIST, chats[:10])
        ActionExecutor.execute_pipeline(ans, actions)

# ================= ПАЙПЛАЙН ИСПОЛНЕНИЯ =================
class ActionExecutor:
    DANGEROUS_ACTIONS = {"DCLICK", "RCLICK", "TYPE", "WINDOW", "SILENT_EXEC", "TERM_EXEC", "TG_SEND"}
    STOP_EVENT = threading.Event()

    @classmethod
    def stop(cls):
        cls.STOP_EVENT.set()

    @staticmethod
    def _confirm_action(act_type, value, gui_instance):
        if act_type not in ActionExecutor.DANGEROUS_ACTIONS:
            return True
        if not Config.CONFIRM_ACTIONS:
            return Config.ALLOW_UNATTENDED_ACTIONS or gui_instance is not None
        if gui_instance is None:
            return Config.ALLOW_UNATTENDED_ACTIONS

        approved = threading.Event()
        result = {"value": False}

        def ask():
            result["value"] = messagebox.askyesno(
                "Подтверждение действия",
                f"Jarvis хочет выполнить:\n\n{act_type}: {value}\n\nРазрешить?",
                parent=gui_instance.root
            )
            approved.set()

        gui_instance.root.after(0, ask)
        approved.wait(timeout=120)
        return result["value"]

    @staticmethod
    def execute_pipeline(ans, actions, gui_instance=None):
        if actions:
            ActionExecutor.STOP_EVENT.clear()
            AudioEngine.speak(ans if len(ans) < 80 else "Выполняю операцию, сэр.")
            for act_type, val in actions:
                if ActionExecutor.STOP_EVENT.is_set():
                    SystemCore.notify("⛔ Выполнение остановлено", 3000)
                    break
                time.sleep(0.12)
                if not ActionExecutor._confirm_action(act_type, val, gui_instance):
                    SystemCore.notify(f"Действие отменено: {act_type}", 3000)
                    continue
                if act_type in ["CLICK", "DCLICK", "RCLICK"]:
                    coords = [int(n) for n in re.findall(r'\d+', val)]
                    if len(coords) >= 2:
                        btn = 1 if act_type in ["CLICK", "DCLICK"] else 3
                        double = (act_type == "DCLICK")
                        InputDriver.mouse_click(coords[0], coords[1], btn=btn, double=double)
                elif act_type == "KEY":
                    InputDriver.press_key(val)
                elif act_type == "TYPE":
                    InputDriver.type_text(val)
                elif act_type == "SCROLL":
                    InputDriver.mouse_scroll(val)
                elif act_type == "WINDOW":
                    SystemCore.window_control(val)
                elif act_type in ["SILENT_EXEC", "TERM_EXEC"]:
                    if Config.ALLOW_SHELL_EXEC:
                        SystemCore.launch(val, is_silent=(act_type == "SILENT_EXEC"), gui_instance=gui_instance)
                    else:
                        SystemCore.notify("Команда заблокирована: включите JARVIS_ALLOW_SHELL_EXEC только для доверенного режима", 5000)
                elif act_type == "TG_SEND":
                    SystemCore.tg_send(val)
                elif act_type == "MEMORY_SAVE":
                    MemoryManager.save_memory(val)
                elif act_type == "SEARCH_FILES":
                    result = FileSearch.format_results(val)
                    if gui_instance:
                        gui_instance.root.after(0, lambda text=result: gui_instance.out.insert(tk.END, f"\n{text}\n"))
                    else:
                        SystemCore.notify(result[:180], 6000)
                elif act_type == "PLUGIN":
                    plugin_name, separator, plugin_value = val.partition("|")
                    result = PluginManager.execute(plugin_name.strip(), plugin_value.strip() if separator else "")
                    if gui_instance:
                        gui_instance.root.after(0, lambda text=result: gui_instance.out.insert(tk.END, f"\n[Плагин]: {text}\n"))
                    else:
                        SystemCore.notify(result[:180], 6000)

            SystemCore.notify("⚡ Действие выполнено", 2000)
            if "```" in ans or len(ans) > 400:
                subprocess.Popen([sys.executable, os.path.abspath(__file__), "--show"])
        else:
            AudioEngine.speak(ans)
            SystemCore.notify(ans[:80], 5000)

# ================= ДЕМОНЫ =================
class SystemDaemons:
    @staticmethod
    def run_sentinel():
        while True:
            try:
                t = SystemCore.run("nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader 2>/dev/null")
                if t and t.isdigit() and int(t) > 83:
                    AudioEngine.speak(f"Внимание. Видеокарта нагрелась до {t} градусов.")
                    SystemCore.tg_send(f"⚠️ GPU Перегрев: {t}°C")

                if os.path.exists("/tmp/j_heal"):
                    with open("/tmp/j_heal", "r", encoding="utf-8") as f:
                        err = f.read().strip()
                    try:
                        os.remove("/tmp/j_heal")
                    except Exception:
                        pass
                    if err:
                        AudioEngine.speak("Ошибка терминала. Открываю протокол восстановления.")
                        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--heal", base64.b64encode(err.encode()).decode()])
            except Exception:
                pass
            time.sleep(15)

    @staticmethod
    def run_clipboard():
        last, hist = "", []
        while True:
            text = SystemCore.get_clipboard(primary=True) or SystemCore.get_clipboard(primary=False)
            if text and text != last and len(text.strip()) > 3:
                last = text
                if text not in hist:
                    hist.insert(0, text)
                    if len(hist) > 5:
                        hist.pop()
            time.sleep(1)

# ================= GUI =================
class JarvisGUI:
    def __init__(self, heal_err=None):
        self.ai = AIProvider()
        self.chats = MemoryManager._load(Config.FILE_HIST, [{"title": "Новый процесс", "messages": []}])
        self.idx = 0
        self.h_cmd, self.h_idx = [], -1
        self.last_ans, self.last_actions = None, []
        self.processing = False

        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S.")
        self.root.configure(bg=Config.UI_BG)
        self.root.attributes('-topmost', True)
        self.root.geometry(f"960x620+{(self.root.winfo_screenwidth()-960)//2}+{(self.root.winfo_screenheight()-620)//2}")

        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=Config.UI_BG, sashwidth=3)
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        # Боковая панель истории
        f_hist = tk.Frame(pane, bg=Config.UI_PANEL)
        pane.add(f_hist, width=240)
        tk.Button(f_hist, text="+ Новый процесс", command=self.new_chat, bg="#313244", fg=Config.UI_TEXT, relief="flat").pack(fill="x", padx=10, pady=10)
        self.lb = tk.Listbox(f_hist, bg=Config.UI_BG, fg=Config.UI_TEXT, selectbackground="#45475a", relief="flat", highlightthickness=0)
        self.lb.pack(fill="both", expand=True, padx=10, pady=5)
        self.lb.bind("<<ListboxSelect>>", self._on_select_chat)

        # Рабочая зона
        f_chat = tk.Frame(pane, bg=Config.UI_BG)
        pane.add(f_chat)

        f_top = tk.Frame(f_chat, bg=Config.UI_BG)
        f_top.pack(fill="x", pady=(0, 5))
        self.status_var = tk.StringVar(value="🟢 Онлайн")
        tk.Label(f_top, textvariable=self.status_var, bg=Config.UI_BG, fg=Config.UI_ACCENT, font=("Consolas", 9, "bold")).pack(side="left", padx=5)
        tk.Button(f_top, text="🔄 Индекс", command=self.reindex, bg=Config.UI_PANEL, fg=Config.UI_TEXT, relief="flat").pack(side="right")
        tk.Button(f_top, text="[⛶ OCR]", command=self.do_ocr, bg=Config.UI_PANEL, fg=Config.UI_ACCENT, relief="flat").pack(side="right", padx=(5, 0))
        tk.Button(f_top, text="🔍 RAG", command=self.do_rag, bg=Config.UI_PANEL, fg=Config.UI_TEXT, relief="flat").pack(side="right")

        f_act = tk.Frame(f_chat, bg=Config.UI_BG)
        f_act.pack(side="bottom", fill="x", pady=(5, 0))
        self.b_snd = tk.Button(f_act, text="Выполнить (Enter)", command=self.send, bg="#89b4fa", fg="#11111b", font=("", 9, "bold"), relief="flat")
        self.b_snd.pack(side="left", padx=(0, 5))
        self.b_stop = tk.Button(f_act, text="Остановить", command=self.stop_actions, bg="#f38ba8", fg="#11111b", relief="flat")
        self.b_stop.pack(side="left", padx=(0, 5))
        self.b_run = tk.Button(f_act, text="Повторить действия", command=self.run_last, bg="#f38ba8", fg="#11111b", font=("", 9, "bold"), relief="flat")
        self.b_cpy = tk.Button(f_act, text="Копировать", command=self.cpy, bg="#45475a", fg=Config.UI_TEXT, relief="flat")

        self.ent = tk.Entry(f_chat, bg=Config.UI_PANEL, fg=Config.UI_ACCENT, insertbackground=Config.UI_ACCENT, font=("Consolas", 11), relief="flat")
        self.ent.pack(side="bottom", fill="x", pady=(5, 5))

        f_txt = tk.Frame(f_chat, bg=Config.UI_BG)
        f_txt.pack(side="top", fill="both", expand=True)
        self.out = tk.Text(f_txt, bg=Config.UI_PANEL, fg=Config.UI_TEXT, font=("Consolas", 10), wrap="word", relief="flat", padx=10, pady=10)
        scr = tk.Scrollbar(f_txt, command=self.out.yview, bg="#313244")
        self.out.configure(yscrollcommand=scr.set)
        scr.pack(side="right", fill="y")
        self.out.pack(side="left", fill="both", expand=True)

        self.ent.focus_set()
        self.ent.bind("<Return>", lambda e: self.send())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.ent.bind("<Up>", self.h_up)
        self.ent.bind("<Down>", self.h_dn)

        self.upd_list()
        self.upd_ui()

        if heal_err:
            try:
                self.ent.insert(0, f"Ошибка терминала. Проанализируй и исправь:\n{base64.b64decode(heal_err).decode()}")
                self.send()
            except Exception:
                pass

    def _on_select_chat(self, e):
        sel = self.lb.curselection()
        if sel:
            self.idx = sel[0]
            self.upd_ui()

    def reindex(self):
        self.status_var.set("🔍 Индексация...")
        def _th():
            SystemScanner.build_full_index()
            OpenRouterManager.get_models(force_refresh=True)
            PluginManager.load()
            self.root.after(0, lambda: self.status_var.set("🟢 Онлайн"))
            SystemCore.notify("✅ База приложений обновлена", 2000)
        threading.Thread(target=_th, daemon=True).start()

    def do_ocr(self):
        self.root.withdraw()
        time.sleep(0.35)
        tmp_img, tmp_txt = "/tmp/j_o.png", "/tmp/j_o"
        cmd = f"grim -g \"$(slurp)\" {tmp_img} 2>/dev/null || spectacle -rbno {tmp_img} 2>/dev/null"
        if subprocess.Popen(cmd, shell=True).wait() == 0 and os.path.exists(tmp_img):
            subprocess.run(f"tesseract {tmp_img} {tmp_txt} -l rus+eng 2>/dev/null", shell=True)
            if os.path.exists(f"{tmp_txt}.txt"):
                with open(f"{tmp_txt}.txt", "r", encoding="utf-8") as f:
                    t = f.read().strip()
                if t:
                    self.ent.delete(0, tk.END)
                    self.ent.insert(0, t)
        self.root.deiconify()
        self.ent.focus_set()

    def do_rag(self):
        q = self.ent.get().strip()
        if q:
            try:
                result = subprocess.run(
                    ["rg", "-m", "2", "-C", "2", "--max-filesize", "50K", "--glob", "!.git", "--glob", "!node_modules", "--glob", "!.cache", "--", q, Config.DIR_PROJ],
                    capture_output=True,
                    text=True,
                    check=False
                )
            except OSError:
                self.out.insert(tk.END, "\n[RAG недоступен: установите ripgrep]\n")
                return
            m = "\n".join(result.stdout.splitlines()[:40]).strip()
            self.out.insert(tk.END, f"\n[Локальный контекст RAG]:\n{m}\n" if m else "\n[Ничего не найдено в проектах]\n")
            self.out.see(tk.END)

    def upd_list(self):
        self.lb.delete(0, tk.END)
        for c in self.chats:
            self.lb.insert(tk.END, c.get("title", "Диалог"))
        if self.chats and 0 <= self.idx < len(self.chats):
            self.lb.selection_set(self.idx)

    def new_chat(self):
        self.chats.insert(0, {"title": "Новый процесс", "messages": []})
        self.idx = 0
        self.upd_list()
        self.upd_ui()

    def upd_ui(self):
        self.out.delete("1.0", tk.END)
        if self.chats and 0 <= self.idx < len(self.chats):
            for m in self.chats[self.idx]["messages"]:
                speaker = 'Пользователь' if m['role'] == 'user' else 'Jarvis'
                self.out.insert(tk.END, f"[{speaker}]:\n{m['content']}\n\n")
        self.out.see(tk.END)

    def h_up(self, e):
        if self.h_cmd and self.h_idx < len(self.h_cmd) - 1:
            self.h_idx += 1
            self.ent.delete(0, tk.END)
            self.ent.insert(0, self.h_cmd[-(self.h_idx + 1)])
        return "break"

    def h_dn(self, e):
        if self.h_idx > 0:
            self.h_idx -= 1
            self.ent.delete(0, tk.END)
            self.ent.insert(0, self.h_cmd[-(self.h_idx + 1)])
        elif self.h_idx == 0:
            self.h_idx = -1
            self.ent.delete(0, tk.END)
        return "break"

    def stop_actions(self):
        ActionExecutor.stop()
        self.status_var.set("⛔ Остановлено")
        SystemCore.notify("Выполнение действий остановлено", 3000)

    def _handle_local_command(self, prompt):
        command, _, value = prompt.partition(" ")
        command = command.lower()
        value = value.strip()
        response = None

        if command in {"/help", "/помощь"}:
            response = (
                "Локальные команды:\n"
                "/help — показать эту справку\n"
                "/status — состояние Jarvis и интеграций\n"
                "/clear — очистить текущий диалог\n"
                "/remember <факт> — сохранить факт в памяти\n"
                "/forget <текст> — удалить совпадающие факты\n"
                "/find <текст> — найти файлы по имени или содержимому\n"
                "/plugins — показать загруженные плагины\n"
                "/remind in 20m <текст> — создать напоминание\n"
                "/tasks — показать активные напоминания\n"
                "/stop — остановить текущие действия"
            )
        elif command == "/status":
            providers = []
            if Config.GROQ_API_KEY:
                providers.append("Groq")
            if Config.OPENROUTER_API_KEY:
                providers.append("OpenRouter")
            response = (
                f"Провайдеры: {', '.join(providers) or 'не настроены'}\n"
                f"Аудио: {'включено' if AUDIO_ENABLED else 'недоступно'}\n"
                f"Скриншоты: {'разрешены' if Config.ALLOW_SCREEN_UPLOAD else 'запрещены'}\n"
                f"Авто-vision: {'включён' if Config.AUTO_SCREEN else 'выключен'}\n"
                f"Shell: {'разрешён' if Config.ALLOW_SHELL_EXEC else 'заблокирован'}"
            )
        elif command == "/clear":
            self.chats[self.idx]["messages"] = []
            response = "Текущий диалог очищен."
        elif command == "/remember" and value:
            MemoryManager.save_memory(value)
            response = "Запомнил."
        elif command == "/forget" and value:
            removed = MemoryManager.forget_memory(value)
            response = f"Удалено фактов: {removed}."
        elif command == "/find" and value:
            self.status_var.set("🔎 Ищу файлы...")
            threading.Thread(target=self._find_async, args=(value,), daemon=True).start()
            return True
        elif command == "/plugins":
            response = PluginManager.prompt_context()
        elif command == "/remind" and value:
            task = self._parse_reminder(value)
            if task:
                title, due_at = task
                task_id = MemoryManager.schedule_task(title, due_at)
                response = f"Напоминание #{task_id} создано: {title}"
            else:
                response = "Формат: /remind in 20m текст или /remind at 18:30 текст"
        elif command == "/tasks":
            tasks = MemoryManager.list_tasks()
            response = "\n".join(
                f"#{task_id} — {title} ({dt.datetime.fromtimestamp(due_at).strftime('%d.%m %H:%M')})"
                for task_id, title, due_at, _ in tasks
            ) or "Активных напоминаний нет."
        elif command == "/stop":
            self.stop_actions()
            response = "Остановил выполнение действий."

        if response is None:
            return False
        self.chats[self.idx]["messages"].append({"role": "assistant", "content": response})
        self.chats[self.idx]["messages"] = self.chats[self.idx]["messages"][-Config.MAX_HISTORY_MESSAGES:]
        MemoryManager._save(Config.FILE_HIST, self.chats[:10])
        self.upd_ui()
        self.status_var.set("🟢 Онлайн")
        return True

    @staticmethod
    def _parse_reminder(value):
        relative = re.match(r"^(?:in|через)\s+(\d+)\s*(s|sec|сек|m|min|мин|минут|минуту|h|hour|ч|час|часа|часов|d|day|д|дн|дней)\s+(.+)$", value, re.IGNORECASE)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2).lower()
            multipliers = {"s": 1, "sec": 1, "сек": 1, "m": 60, "min": 60, "мин": 60, "минут": 60, "минуту": 60, "h": 3600, "hour": 3600, "ч": 3600, "час": 3600, "часа": 3600, "часов": 3600, "d": 86400, "day": 86400, "д": 86400, "дн": 86400, "дней": 86400}
            return relative.group(3).strip(), time.time() + amount * multipliers[unit]
        clock = re.match(r"^(?:at|в)\s+(\d{1,2}):(\d{2})\s+(.+)$", value, re.IGNORECASE)
        if clock:
            now = dt.datetime.now()
            due = now.replace(hour=int(clock.group(1)), minute=int(clock.group(2)), second=0, microsecond=0)
            if due.timestamp() <= time.time():
                due += dt.timedelta(days=1)
            return clock.group(3).strip(), due.timestamp()
        return None

    def _find_async(self, query):
        response = FileSearch.format_results(query)

        def apply_result():
            self.chats[self.idx]["messages"].append({"role": "assistant", "content": response})
            self.chats[self.idx]["messages"] = self.chats[self.idx]["messages"][-Config.MAX_HISTORY_MESSAGES:]
            MemoryManager._save(Config.FILE_HIST, self.chats[:10])
            self.upd_ui()
            self.status_var.set("🟢 Онлайн")

        self.root.after(0, apply_result)

    def send(self):
        p = self.ent.get().strip()
        if not p or self.processing:
            return
        if not self.h_cmd or self.h_cmd[-1] != p:
            self.h_cmd.append(p)
        self.h_idx = -1
        self.ent.delete(0, tk.END)

        c = self.chats[self.idx]
        if not c["messages"]:
            c["title"] = p[:22]
        c["messages"].append({"role": "user", "content": p})

        self.upd_ui()
        self.upd_list()
        if self._handle_local_command(p):
            return
        self.processing = True
        self.status_var.set("🟡 Думаю...")
        self.b_run.pack_forget()
        self.b_cpy.pack_forget()
        threading.Thread(target=self._proc, args=(c, p), daemon=True).start()

    def _proc(self, c, text):
        try:
            needs_vis = Config.AUTO_SCREEN or any(w in text.lower() for w in ["экран", "окн", "видит", "смотри", "клик", "нажми", "где", "кнопк", "блок"])
            scr = SystemCore.capture_screen() if needs_vis and Config.ALLOW_SCREEN_UPLOAD else None
            meta = SystemCore.get_active_window_title()

            ans, actions = self.ai.ask(c["messages"], scr, meta)
            c["messages"].append({"role": "assistant", "content": ans})
            c["messages"] = c["messages"][-Config.MAX_HISTORY_MESSAGES:]
            MemoryManager._save(Config.FILE_HIST, self.chats[:10])

            self.root.after(0, lambda: self._apply_result_ui(ans, actions))
            ActionExecutor.execute_pipeline(ans, actions, gui_instance=self)
        except Exception as exc:
            LOGGER.exception("Ошибка обработки запроса")
            self.root.after(0, lambda: self._apply_error_ui(str(exc)))

    def _apply_result_ui(self, ans, actions):
        self.processing = False
        self.last_ans, self.last_actions = ans, actions
        self.upd_ui()
        self.b_cpy.pack(side="left", padx=5)
        if actions:
            self.out.insert(tk.END, f"⚡ Выполненные действия: {actions}\n")
            self.b_run.pack(side="left", padx=5)
        self.status_var.set("🟢 Онлайн")
        self.out.see(tk.END)

    def _apply_error_ui(self, error):
        self.processing = False
        self.status_var.set("🔴 Ошибка")
        self.out.insert(tk.END, f"\n[Ошибка обработки]: {error}\n")
        self.out.see(tk.END)
        SystemCore.notify("Не удалось обработать запрос", 5000)

    def cpy(self):
        if self.last_ans:
            SystemCore.copy_to_clipboard(self.last_ans)
            AudioEngine.speak("Скопировано.")

    def run_last(self):
        if self.last_actions:
            threading.Thread(
                target=lambda: ActionExecutor.execute_pipeline(self.last_ans, self.last_actions, gui_instance=self),
                daemon=True
            ).start()

# ================= ТОЧКА ВХОДА =================
TRAY_GUI_PROCESS = None


def _find_jarvis_window(action):
    commands = []
    if shutil.which("kdotool"):
        commands.append(["kdotool", "search", "--name", "J.A.R.V.I.S.", action])
    if shutil.which("xdotool"):
        commands.append(["xdotool", "search", "--name", "J.A.R.V.I.S.", action])
    for command in commands:
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if result.returncode == 0:
                return True
        except OSError:
            continue
    return False


def create_tray():
    global TRAY_GUI_PROCESS
    try:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")
        else:
            os.environ.setdefault("PYSTRAY_BACKEND", "xorg")
        import pystray
        img = Image.new('RGB', (64, 64), color=(17, 17, 27))
        ImageDraw.Draw(img).ellipse((16, 16, 48, 48), fill=(243, 139, 168))

        def open_gui(icon, item):
            global TRAY_GUI_PROCESS
            try:
                if _find_jarvis_window("windowactivate"):
                    _find_jarvis_window("windowraise")
                    return
                if TRAY_GUI_PROCESS and TRAY_GUI_PROCESS.poll() is None:
                    return
                TRAY_GUI_PROCESS = subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__)],
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    env=SystemCore.get_env()
                )
            except OSError as exc:
                LOGGER.error("Не удалось открыть GUI из трея: %s", exc)

        def show_gui(icon, item):
            open_gui(icon, item)

        def hide_gui(icon, item):
            if not _find_jarvis_window("windowminimize"):
                LOGGER.info("Окно Jarvis не найдено для сворачивания")

        def refresh_models(icon, item):
            threading.Thread(
                target=lambda: (
                    OpenRouterManager.get_models(force_refresh=True),
                    SystemCore.notify("Модели обновлены", 2000)
                ),
                daemon=True
            ).start()

        def stop_actions(icon, item):
            ActionExecutor.stop()
            SystemCore.notify("Выполнение действий остановлено", 2500)

        def quit_tray(icon, item):
            global TRAY_GUI_PROCESS
            if TRAY_GUI_PROCESS and TRAY_GUI_PROCESS.poll() is None:
                TRAY_GUI_PROCESS.terminate()
            icon.stop()

        m = pystray.Menu(
            pystray.MenuItem("Открыть", open_gui, default=True),
            pystray.MenuItem("Показать окно", show_gui),
            pystray.MenuItem("Скрыть окно", hide_gui),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Обновить модели", refresh_models),
            pystray.MenuItem("Остановить действия", stop_actions),
            pystray.MenuItem("Выход", quit_tray)
        )
        pystray.Icon("J", img, "Jarvis", menu=m).run()
    except ImportError:
        LOGGER.error("Трей недоступен: установите pystray и GTK/AppIndicator backend; запускаю GUI вместо трея")
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            env=SystemCore.get_env()
        )
    except Exception as exc:
        LOGGER.exception("Ошибка трей-режима: %s", exc)

if __name__ == "__main__":
    if not any(flag in sys.argv for flag in ["--fix-layout", "--reindex", "--models"]):
        TaskScheduler().start()
    if "--fix-layout" in sys.argv:
        SystemCore.fix_layout()
        sys.exit(0)
    elif "--heal" in sys.argv:
        err_arg = sys.argv[sys.argv.index("--heal") + 1] if len(sys.argv) > sys.argv.index("--heal") + 1 else None
        JarvisGUI(heal_err=err_arg).root.mainloop()
    elif "--reindex" in sys.argv:
        SystemScanner.build_full_index()
        OpenRouterManager.get_models(force_refresh=True)
        PluginManager.load()
        print("База приложений и кэш моделей успешно обновлены.")
        sys.exit(0)
    elif "--models" in sys.argv:
        models = OpenRouterManager.get_models(force_refresh=True)
        print(f"Vision (Free): {[m['id'] for m in models['free_vision']]}")
        print(f"Text (Free): {[m['id'] for m in models['free_text'][:5]]}")
        sys.exit(0)
    elif "--tray" in sys.argv or "--daemon" in sys.argv:
        threading.Thread(target=SystemScanner.build_full_index, daemon=True).start()
        threading.Thread(target=OpenRouterManager.get_models, daemon=True).start()
        threading.Thread(target=SystemDaemons.run_clipboard, daemon=True).start()
        threading.Thread(target=SystemDaemons.run_sentinel, daemon=True).start()
        if AUDIO_ENABLED:
            AudioEngine(AIProvider()).start()
        create_tray()
    else:
        JarvisGUI().root.mainloop()
