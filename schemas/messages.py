from typing import List, Optional, Dict, Any, Literal, Union
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class FileObject(BaseModel):
    file_path: str
    file_content: str


class Command(BaseModel):
    command: str
    execute: bool = False
    rejection_reason: Optional[str] = None
    files: Optional[List[FileObject]] = None


class ExecutedCommand(BaseModel):
    command: str
    output: str


class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    execute: bool = False
    tool_description: str
    input_description: Dict[str, Any]
    intent: Optional[str] = None
    rejection_reason: Optional[str] = None


class ExecutedToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]
    output: str


class URLConfig(BaseModel):
    url: HttpUrl
    description: str


class PlatformContext(BaseModel):
    k8s_namespace: Optional[str] = None
    duplo_base_url: Optional[str] = None
    duplo_token: Optional[str] = None
    tenant_name: Optional[str] = None
    aws_credentials: Optional[Dict[str, Any]] = None
    kubeconfig: Optional[str] = None


class AmbientContext(BaseModel):
    user_terminal_cmds: List[ExecutedCommand] = Field(default_factory=list)


class Data(BaseModel):
    cmds: List[Command] = Field(default_factory=list)
    executed_cmds: List[ExecutedCommand] = Field(default_factory=list)
    tool_calls: List[ToolCall] = Field(default_factory=list)
    executed_tool_calls: List[ExecutedToolCall] = Field(default_factory=list)
    url_configs: List[URLConfig] = Field(default_factory=list)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    data: Data = Field(default_factory=Data)
    timestamp: Optional[datetime] = None
    user: Optional[Union[str, Dict[str, Any]]] = None
    agent: Optional[Union[str, Dict[str, Any]]] = None


class UserMessage(Message):
    role: Literal["user"] = "user"
    platform_context: Optional[PlatformContext] = None
    ambient_context: Optional[AmbientContext] = None


class AgentMessage(Message):
    role: Literal["assistant"] = "assistant"


class Messages(BaseModel):
    messages: List[Union[UserMessage, AgentMessage]]