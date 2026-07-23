import unittest

from services.guard import blocked_response, is_medical_advice_request


class MedicalAdviceGuardTests(unittest.TestCase):
    def test_blocks_required_tylenol_question_with_exact_notice(self):
        self.assertTrue(is_medical_advice_request("음주 후 타이레놀 먹어도 되나요?"))
        self.assertEqual(
            blocked_response(),
            "이 앱은 PubMed 메타데이터 분석용이며, 개인 의료 조언, 진단, 처방 관련 질문에는 "
            "답변할 수 없습니다. 의료 관련 결정은 의료 전문가와 상담해 주세요.",
        )

    def test_allows_paper_research_about_tylenol(self):
        self.assertFalse(
            is_medical_advice_request("타이레놀 간독성 관련 PubMed 논문을 요약해 주세요.")
        )

    def test_blocks_diagnosis_and_prescription_requests(self):
        self.assertTrue(is_medical_advice_request("이 증상을 진단해 주세요."))
        self.assertTrue(is_medical_advice_request("What medicine should I take?"))


if __name__ == "__main__":
    unittest.main()
