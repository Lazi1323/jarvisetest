import shutil
import subprocess


def _status(_value):
    commands = ["python3", "rg", "fd", "mpv", "grim", "ydotool", "wtype"]
    available = [name for name in commands if shutil.which(name)]
    return "Доступные утилиты: " + ", ".join(available)


def register(api):
    api.register_action("SYSTEM_STATUS", "проверить системные утилиты", _status)
