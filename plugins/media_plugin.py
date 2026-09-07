import shutil
import subprocess


def _playerctl(action):
    if not shutil.which("playerctl"):
        return "playerctl не установлен."
    result = subprocess.run(["playerctl", action], capture_output=True, text=True, check=False)
    return result.stdout.strip() or ("Готово." if result.returncode == 0 else result.stderr.strip() or "Медиакоманда завершилась с ошибкой.")


def register(api):
    api.register_action("MEDIA_PLAY", "возобновить музыку", lambda value: _playerctl("play"))
    api.register_action("MEDIA_PAUSE", "поставить музыку на паузу", lambda value: _playerctl("pause"))
    api.register_action("MEDIA_NEXT", "следующий трек", lambda value: _playerctl("next"))
    api.register_action("MEDIA_STATUS", "текущий трек", lambda value: _playerctl("metadata"))
