from enum import Enum

class Strategy(str, Enum):
    """文档转换的处理策略。"""
    AUTO = "auto"
    FAST = "fast"
    DEEP = "deep"
