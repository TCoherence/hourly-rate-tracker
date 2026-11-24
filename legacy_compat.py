"""Optional local-only compatibility mapping for legacy provider names.

The mapping lives beside local adapters, not in the source tree or exports.
Unknown or malformed mappings are never interpreted as a working connection.
"""
from pathlib import Path
import json
import os
import re

COMPAT_FILE = Path("adapters") / "legacy-compat.json"
KNOWN_PROVIDERS = frozenset(("disabled", "system", "verified_system", "script", "cisco"))
ADAPTER_PATH_ENV = "HOURLY_RATE_ADAPTER_LEGACY_PATH"


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("本机旧版兼容配置含重复字段")
        result[key] = value
    return result


def load_compat(directory):
    path = Path(directory) / COMPAT_FILE
    try:
        if path.stat().st_size > 16384:
            raise ValueError("本机旧版兼容配置过大")
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)
    except FileNotFoundError:
        return {"providers": {}, "environment": {}}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("本机旧版兼容配置无法读取") from error
    if not isinstance(raw, dict) or set(raw) != {"version", "providers", "environment"} or raw["version"] != 1 or type(raw["version"]) is not int:
        raise ValueError("本机旧版兼容配置格式无效")
    providers, environment = raw["providers"], raw["environment"]
    if not isinstance(providers, dict) or not isinstance(environment, dict) or len(providers) > 32 or len(environment) > 8:
        raise ValueError("本机旧版兼容配置格式无效")
    for name, config in providers.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}", name) or name in KNOWN_PROVIDERS:
            raise ValueError("本机旧版兼容配置包含无效来源")
        if not isinstance(config, dict) or config not in ({"provider": "verified_system"}, {"provider": "script", "status_script_path": "local_adapter"}):
            raise ValueError("本机旧版兼容配置包含无效迁移规则")
    for name, target in environment.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", name) or name == ADAPTER_PATH_ENV or target != ADAPTER_PATH_ENV:
            raise ValueError("本机旧版兼容配置包含无效环境变量")
    return {"providers": providers, "environment": environment}


def migrate_settings(settings, directory, local_script):
    result = dict(settings)
    provider = result.get("provider", "disabled")
    if not isinstance(provider, str):
        raise ValueError("状态来源格式无效")
    if provider in KNOWN_PROVIDERS:
        return result
    aliases = load_compat(directory)["providers"] if directory is not None else {}
    config = aliases.get(provider)
    if config is None:
        raise ValueError("不支持的旧版状态来源；请检查本机旧版兼容配置")
    result["provider"] = config["provider"]
    if config.get("status_script_path") == "local_adapter":
        result["status_script_path"] = local_script
    return result


def legacy_provider_for_log(name, directory):
    if not isinstance(name, str):
        return None
    if name in KNOWN_PROVIDERS:
        return name
    try:
        config = load_compat(directory)["providers"].get(name)
    except ValueError:
        return None
    if not config:
        return None
    return "legacy_script" if config["provider"] == "script" else config["provider"]


def adapter_environment(directory, environ, strict=False):
    # A new explicit setting wins over its legacy equivalent.
    value = environ.get(ADAPTER_PATH_ENV)
    if not value:
        # A malformed file cannot safely be interpreted as "no legacy path":
        # that could let a script fall back to a different executable.
        aliases = load_compat(directory)["environment"] if directory is not None else {}
        value = next((environ.get(name) for name in aliases if environ.get(name)), None)
    if value and isinstance(value, str) and len(value) <= 4096 and os.path.isabs(value) and "\x00" not in value:
        return {ADAPTER_PATH_ENV: value}
    if value and strict:
        raise ValueError("自定义状态适配器路径必须是有效绝对路径")
    return {}
