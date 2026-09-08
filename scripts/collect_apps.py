#!/usr/bin/env python3
"""Collect installed Linux applications into a JSON index."""

import argparse
import glob
import json
import os
import shutil
import subprocess
from pathlib import Path


DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
]
APP_DIRS = [
    os.path.expanduser("~/Applications"),
    os.path.expanduser("~/AppImages"),
    os.path.expanduser("~/Downloads"),
    "/opt",
]


def desktop_value(values, key):
    value = values.get(key, "")
    return value.split(";", 1)[0].strip()


def collect_desktop_apps():
    apps = []
    seen = set()
    for directory in DESKTOP_DIRS:
        if not os.path.isdir(directory):
            continue
        for path in glob.glob(os.path.join(directory, "**", "*.desktop"), recursive=True):
            real_path = os.path.realpath(path)
            if real_path in seen:
                continue
            seen.add(real_path)
            values = {}
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    for raw_line in stream:
                        line = raw_line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, value = line.split("=", 1)
                            values.setdefault(key, value)
            except OSError:
                continue
            if values.get("NoDisplay", "").lower() == "true":
                continue
            name = desktop_value(values, "Name")
            command = desktop_value(values, "Exec")
            if not name or not command:
                continue
            apps.append({
                "name": name,
                "type": "desktop",
                "command": command,
                "desktop_file": path,
                "keywords": desktop_value(values, "Keywords"),
                "source": "desktop",
            })
    return apps


def collect_flatpaks():
    if not shutil.which("flatpak"):
        return []
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application,name,version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    apps = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        app_id, name = parts[0].strip(), parts[1].strip()
        version = parts[2].strip() if len(parts) > 2 else ""
        apps.append({
            "name": name or app_id,
            "type": "flatpak",
            "id": app_id,
            "version": version,
            "command": f"flatpak run {app_id}",
            "source": "flatpak",
        })
    return apps


def collect_path_apps():
    apps = []
    seen = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory or not os.path.isdir(directory):
            continue
        try:
            for entry in os.scandir(directory):
                if not entry.is_file() or not os.access(entry.path, os.X_OK):
                    continue
                real_path = os.path.realpath(entry.path)
                if real_path in seen:
                    continue
                seen.add(real_path)
                apps.append({
                    "name": entry.name,
                    "type": "binary",
                    "command": entry.path,
                    "source": "PATH",
                })
        except OSError:
            continue
    return apps


def collect_extra_apps():
    apps = []
    seen = set()
    for directory in APP_DIRS:
        if not os.path.isdir(directory):
            continue
        for root, dirs, files in os.walk(directory):
            dirs[:] = [name for name in dirs if name not in {".git", "node_modules", ".cache"}]
            for filename in files:
                path = os.path.join(root, filename)
                if not os.access(path, os.X_OK):
                    continue
                real_path = os.path.realpath(path)
                if real_path in seen:
                    continue
                lower_name = filename.lower()
                if not (lower_name.endswith(".appimage") or ".appimage" in lower_name or filename.endswith(".sh")):
                    continue
                seen.add(real_path)
                apps.append({
                    "name": filename,
                    "type": "appimage" if "appimage" in lower_name else "script",
                    "command": path,
                    "source": directory,
                })
    return apps


def deduplicate(apps):
    result = []
    seen = set()
    for app in apps:
        key = (app.get("type"), app.get("id") or app.get("command"), app.get("name"))
        if key in seen:
            continue
        seen.add(key)
        result.append(app)
    return sorted(result, key=lambda item: (item.get("name", "").lower(), item.get("type", "")))


def collect_all():
    apps = []
    apps.extend(collect_desktop_apps())
    apps.extend(collect_flatpaks())
    apps.extend(collect_path_apps())
    apps.extend(collect_extra_apps())
    return deduplicate(apps)


def main():
    parser = argparse.ArgumentParser(description="Собрать приложения Linux в JSON")
    parser.add_argument("-o", "--output", default="apps_index.json", help="путь к JSON-файлу")
    args = parser.parse_args()

    apps = collect_all()
    output = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "count": len(apps),
        "applications": apps,
    }
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {}
    for app in apps:
        counts[app["type"]] = counts.get(app["type"], 0) + 1
    print(f"Собрано приложений: {len(apps)}")
    for app_type, count in sorted(counts.items()):
        print(f"  {app_type}: {count}")
    print(f"Индекс сохранён: {output_path}")


if __name__ == "__main__":
    main()
