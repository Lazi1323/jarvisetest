# Плагины Jarvis

Плагин должен содержать функцию `register(api)` и регистрировать действия:

```python
def register(api):
    api.register_action("MY_ACTION", "описание действия", lambda value: "результат")
```

Плагины из этого каталога и `~/.config/jarvis/plugins` загружаются при старте. В prompt действие вызывается как `PLUGIN: MY_ACTION | аргументы`.
