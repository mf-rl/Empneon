import json
import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8765,
    "debug": True,
    "database": "ai_sims_memory.sqlite3",
    "core_database": "empneon_core.sqlite3",
    "memory_database": "empneon_core_memory.sqlite3",
    "preserve_memory_only_on_game_save": False,
    "response_rejection_enabled": True,
    "active_agent_limit": 1,
    "agent_wake_timeout_seconds": 60,
    "provider": "lmstudio",
    "providers": {
        "lmstudio": {"endpoint": "http://127.0.0.1:1234/api/v1", "model": "local-model"},
        "ollama": {"endpoint": "http://127.0.0.1:11434/v1", "model": "llama3"},
        "openai": {"endpoint": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
        "openrouter": {
            "endpoint": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-4.1-mini",
        },
        "llamacpp": {"endpoint": "http://127.0.0.1:8080/v1", "model": "local-model"},
        "koboldcpp": {"endpoint": "http://127.0.0.1:5001/v1", "model": "local-model"},
        "textgenwebui": {"endpoint": "http://127.0.0.1:5000/v1", "model": "local-model"},
    },
    "models": {
        "small": {
            "temperature": 0.4,
            "max_tokens": 120,
            "context_tokens": 2048,
            "latency_ms": 30000,
            "ram_mb": 64,
            "vram_mb": 0,
        },
        "large": {
            "temperature": 0.6,
            "max_tokens": 300,
            "context_tokens": 4096,
            "latency_ms": 90000,
            "ram_mb": 128,
            "vram_mb": 0,
        },
    },
    "memory": {
        "recent_limit": 6,
        "summary_every": 10,
        "summary_limit": 30,
    },
    "tts": {
        "enabled": False,
        "provider": "piper",
        "endpoint": "",
    },
}


def deep_update(base, overrides):
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config(config_path, environment, error_stream):
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(config_path, encoding="utf-8") as handle:
            deep_update(config, json.load(handle))
    except FileNotFoundError:
        pass
    except Exception as exc:
        error_stream.write(f"Could not read config {config_path}: {exc}\n")

    if environment.get("AI_SIM_PROVIDER"):
        config["provider"] = environment["AI_SIM_PROVIDER"]
    if environment.get("AI_SIM_LLM_BASE_URL"):
        provider = config.get("provider") or "lmstudio"
        config.setdefault("providers", {}).setdefault(provider, {})["endpoint"] = environment[
            "AI_SIM_LLM_BASE_URL"
        ]
    if environment.get("AI_SIM_MODEL"):
        provider = config.get("provider") or "lmstudio"
        config.setdefault("providers", {}).setdefault(provider, {})["model"] = environment[
            "AI_SIM_MODEL"
        ]
        for task in ("small", "large"):
            config.setdefault("models", {}).setdefault(task, {})["model"] = environment[
                "AI_SIM_MODEL"
            ]
    if environment.get("AI_SIM_DB"):
        config["memory_database"] = environment["AI_SIM_DB"]
    if environment.get("AI_SIM_MEMORY_DB"):
        config["memory_database"] = environment["AI_SIM_MEMORY_DB"]
    if environment.get("AI_SIM_PORT"):
        config["port"] = int(environment["AI_SIM_PORT"])
    if environment.get("AI_SIM_HOST"):
        config["host"] = environment["AI_SIM_HOST"]
    return config


def setup_logging(root, config, error_stream):
    log_dir = os.path.join(root, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = tempfile.gettempdir()
    root_logger = logging.getLogger("ai_sims")
    root_logger.setLevel(logging.DEBUG if config.get("debug") else logging.INFO)
    if root_logger.handlers:
        return root_logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in ("agent_manager", "ai_provider", "memory"):
        handler = RotatingFileHandler(
            os.path.join(log_dir, name + ".log"), maxBytes=512000, backupCount=3
        )
        handler.setFormatter(formatter)
        logging.getLogger("ai_sims." + name).addHandler(handler)
        logging.getLogger("ai_sims." + name).setLevel(root_logger.level)
    stream = logging.StreamHandler(error_stream)
    stream.setFormatter(formatter)
    root_logger.addHandler(stream)
    return root_logger
