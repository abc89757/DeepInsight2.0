from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


DatabaseType = Literal["mysql", "postgresql", "neo4j"]


class DatabaseConnection(BaseModel):
    """前端传来的数据库连接配置。"""

    type: DatabaseType = Field(default="mysql", description="数据库类型")
    alias: str = Field(..., min_length=1, description="连接名称")
    host: str = Field(..., min_length=1, description="数据库主机地址")
    port: int = Field(..., gt=0, le=65535, description="数据库端口")
    user: str = Field(..., min_length=1, description="用户名")
    password: str = Field(default="", description="密码")
    database: Optional[str] = Field(default=None, description="数据库名")


class DatabaseServerConnection(BaseModel):
    """用于发现服务器下可用数据库的连接配置。"""

    type: DatabaseType = Field(default="mysql", description="数据库类型")
    host: str = Field(..., min_length=1, description="数据库主机地址")
    port: int = Field(..., gt=0, le=65535, description="数据库端口")
    user: str = Field(..., min_length=1, description="用户名")
    password: str = Field(default="", description="密码")


class TestConnectionResponse(BaseModel):
    """测试数据库连接接口的返回结果。"""

    success: bool
    message: str
    database_type: str
    alias: str
    server_info: Optional[str] = None


class CreateTaskRequest(BaseModel):
    """创建分析任务时前端传来的数据。"""

    question: str = Field(..., min_length=1, description="用户输入的自然语言分析需求")
    connection_id: str = Field(..., min_length=1, description="系统库中保存的数据库连接 ID")
    scene: str = Field(default="general", description="业务场景，当前先默认 general")
    report_depth: str = Field(default="standard", description="报告深度，当前先默认 standard")


class AnalysisTaskContext(BaseModel):
    """后端内部执行分析任务时使用的完整上下文。"""

    question: str
    connection_id: str
    database_alias: str
    database: DatabaseConnection
    scene: str = "general"
    report_depth: str = "standard"


class TaskResponse(BaseModel):
    """创建分析任务后的返回结果。"""

    success: bool
    message: str
    task_id: str
    status: str
    stage: str
    task: Dict[str, Any]
