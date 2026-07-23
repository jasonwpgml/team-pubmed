"""Server-side policy guard for medical advice requests."""

from __future__ import annotations

import re

BLOCKED_PATTERNS = (
    r"(진단|처방|복용량|투약량|치료법.*추천)",
    r"(약|타이레놀|아세트아미노펜|진통제|항생제|소염제).{0,20}(먹|복용|바꿔|끊어|같이)",
    r"(diagnos|prescri|dosage|should i take|what medicine)",
)

BLOCKED_RESPONSE = (
    "이 앱은 PubMed 메타데이터 분석용이며, 개인 의료 조언, 진단, 처방 관련 질문에는 "
    "답변할 수 없습니다. 의료 관련 결정은 의료 전문가와 상담해 주세요."
)


def is_medical_advice_request(message: str) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in BLOCKED_PATTERNS)


def blocked_response() -> str:
    return BLOCKED_RESPONSE
