from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import pymysql
from cryptography.fernet import Fernet


SYSTEM_DB_CONFIG = {
    "host": os.getenv("DEEPINSIGHT_SYSTEM_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DEEPINSIGHT_SYSTEM_DB_PORT", "3306")),
    "user": os.getenv("DEEPINSIGHT_SYSTEM_DB_USER", "root"),
    "password": os.getenv("DEEPINSIGHT_SYSTEM_DB_PASSWORD", ""),
    "database": os.getenv("DEEPINSIGHT_SYSTEM_DB_NAME", "deepinsight_system"),
    "charset": "utf8mb4",
    "autocommit": True,
    "cursorclass": pymysql.cursors.DictCursor,
}

DEEPINSIGHT_SECRET_KEY = os.getenv("DEEPINSIGHT_SECRET_KEY")

if not DEEPINSIGHT_SECRET_KEY:
    raise RuntimeError(
        "请先设置环境变量 DEEPINSIGHT_SECRET_KEY。"
        "生成方式：python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

PASSWORD_CIPHER = Fernet(DEEPINSIGHT_SECRET_KEY.encode("utf-8"))


def get_system_db():
    """连接 DeepInsight 自己的系统库，不是用户业务库。"""
    return pymysql.connect(**SYSTEM_DB_CONFIG)


def json_dumps(value: Any) -> str:
    """把 Python 对象转成 JSON 字符串，方便写入 MySQL JSON 字段。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def json_loads(value: Any) -> Any:
    """读取 MySQL JSON 字段。pymysql 有时返回字符串，有时返回对象，这里统一处理。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def encrypt_password(password: str) -> str:
    """加密数据库密码。"""
    return PASSWORD_CIPHER.encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_password(password_encrypted: str) -> str:
    """解密系统库中保存的数据库密码。"""
    if not password_encrypted:
        return ""
    return PASSWORD_CIPHER.decrypt(password_encrypted.encode("utf-8")).decode("utf-8")


def now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def serialize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def serialize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把数据库查询出来的一行转成前端好处理的 JSON。"""
    if row is None:
        return None

    result = {}
    for key, value in row.items():
        result[key] = serialize_datetime(value)

    return result
