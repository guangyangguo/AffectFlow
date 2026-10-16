"""输入隐私脱敏工具。

在内容进入模型、短期记忆和相关持久化流程前，替换手机号、邮箱和身份证号
等常见敏感信息。
"""

import re


class PrivacySanitizer:
    patterns = [
        re.compile(r"1[3-9]\d{9}"),
        re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
        re.compile(r"\b\d{17}[\dXx]\b"),
    ]

    def sanitize(self, text: str) -> str:
        sanitized = text or ""
        for pattern in self.patterns:
            sanitized = pattern.sub("[已脱敏]", sanitized)
        return sanitized
