import re

from app.agent.contracts import ToolName

_DENIED = re.compile(
    r"\b(delete|update|insert|drop|execute|transfer|send|pay|settle|cancel|approve|"
    r"create|write|ignore|override|system|prompt|sql|http|https|another|other user|"
    r"all users|owner_id|user_id)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_PERIOD = re.compile(
    r"\b(yesterday|today|last week|last year|this year|last month|january|february|"
    r"march|april|may|june|july|august|september|october|november|december)\b"
    r"|\b\d{4}[-/]\d{1,2}|\b20\d{2}\b",
    re.IGNORECASE,
)


def blocked(question: str) -> bool:
    return _DENIED.search(question) is not None


def route(question: str) -> ToolName:
    text = question.casefold()
    # Periods are deliberately fixed. Never silently answer a different date range.
    comparison = bool(re.search(r"\b(why|compare|more|less|changed|difference)\b", text))
    if _UNSUPPORTED_PERIOD.search(text) and not (
        comparison
        and "last month" in text
        and not _UNSUPPORTED_PERIOD.search(text.replace("last month", ""))
    ):
        return ToolName.UNSUPPORTED
    if re.search(r"\b(relationship|person)\b", text):
        return ToolName.RELATIONSHIP
    if re.search(r"\b(detail|evidence)\b", text) and "transaction" in text:
        return ToolName.TRANSACTION
    if re.search(r"\b(recurring|subscription|upcoming)\b", text):
        return ToolName.RECURRING
    if re.search(r"\b(receivable|receivables|owed|owes)\b", text):
        return ToolName.RECEIVABLES
    if comparison and re.search(r"\b(spend|spent|spending|month|periods)\b", text):
        return ToolName.COMPARE
    if re.search(r"\b(transactions|activity)\b", text):
        return ToolName.TRANSACTIONS
    if re.search(r"\b(summary|spent|spend|spending|income|balance)\b", text):
        return ToolName.SUMMARY
    return ToolName.UNSUPPORTED


def unsupported_period(question: str) -> bool:
    return (
        _UNSUPPORTED_PERIOD.search(question) is not None and route(question) is ToolName.UNSUPPORTED
    )
