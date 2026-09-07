from datetime import datetime


def register(api):
    api.register_action("TIME_NOW", "текущее локальное время", lambda _: datetime.now().strftime("%d.%m.%Y %H:%M:%S"))