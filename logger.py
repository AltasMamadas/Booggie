"""
Logging estruturado para o Lexico. Logs vão para stdout (capturados
pelo Render automaticamente). Formato: JSON compacto, fácil de parsear.
"""
import json
import time
import logging
import os

_logger = logging.getLogger("lexico")
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.DEBUG if os.environ.get("FLASK_ENV") != "production" else logging.INFO)


def _emit(level, event, **kw):
    entry = {"t": round(time.time(), 2), "event": event, **kw}
    getattr(_logger, level)(json.dumps(entry, ensure_ascii=False, default=str))


def info(event, **kw):
    _emit("info", event, **kw)


def warn(event, **kw):
    _emit("warning", event, **kw)


def error(event, **kw):
    _emit("error", event, **kw)


def debug(event, **kw):
    _emit("debug", event, **kw)


# Contadores em memória para analytics básico (resetam com o processo)
_counters = {}


def count(metric):
    _counters[metric] = _counters.get(metric, 0) + 1


def get_counts():
    return dict(_counters)
