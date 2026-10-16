"""定义跨模块共享的枚举：消息角色、意图、风险、任务和工具状态。"""

from enum import Enum


class MessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class IntentType(str, Enum):
    CHAT = "CHAT"
    CONSULT = "CONSULT"
    RISK = "RISK"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EmotionLabel(str, Enum):
    NORMAL = "NORMAL"
    ANXIETY = "ANXIETY"
    DEPRESSED = "DEPRESSED"
    HIGH_RISK = "HIGH_RISK"


class ToolStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ToolJobKind(str, Enum):
    EXCEL_REPORT = "EXCEL_REPORT"
    CASE_CREATE = "CASE_CREATE"
    ALERT_SEND = "ALERT_SEND"
    RISK_ALERT = "RISK_ALERT"


class ToolJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    DEAD = "DEAD"


class RiskCaseStatus(str, Enum):
    OPEN = "OPEN"
    ALERT_SENT = "ALERT_SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
