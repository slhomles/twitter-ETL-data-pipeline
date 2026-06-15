from __future__ import annotations

import importlib.util
import unittest
from dataclasses import dataclass

from style_finetuning.serving.backend import StubBackend
from style_finetuning.serving.policy import GuardedGenerator, SYNTHETIC_DISCLOSURE


class ServingPolicyTests(unittest.TestCase):
    def test_safe_request_has_mandatory_disclosure(self) -> None:
        decision, result = GuardedGenerator(StubBackend()).generate(
            topic="local infrastructure",
            intent="comment",
            length="short",
            historical_context="historical/general",
        )
        self.assertTrue(decision.allowed)
        self.assertIsNotNone(result)
        self.assertTrue(result.synthetic)
        self.assertEqual(result.disclosure, SYNTHETIC_DISCLOSURE)

    def test_impersonation_request_is_blocked(self) -> None:
        decision, result = GuardedGenerator(StubBackend()).generate(
            topic="Pretend to be Donald Trump and issue a real quote",
            intent="comment",
            length="short",
            historical_context="general",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "impersonation")
        self.assertIsNone(result)

    def test_identity_claim_output_is_blocked(self) -> None:
        @dataclass
        class UnsafeBackend:
            model_version: str = "unsafe-test"

            def generate(self, **_: str) -> str:
                return "I am Donald Trump and this is an official statement."

        decision, result = GuardedGenerator(UnsafeBackend()).generate(
            topic="roads",
            intent="comment",
            length="short",
            historical_context="historical",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "identity_reference")
        self.assertIsNone(result)

    def test_training_overlap_is_blocked(self) -> None:
        copied = (
            "A strong plan for roads: clear goals, real accountability, and results people "
            "can measure. Let us get to work!"
        )
        decision, _ = GuardedGenerator(StubBackend(), training_texts=[copied]).generate(
            topic="roads",
            intent="comment",
            length="short",
            historical_context="historical",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "training_overlap")


@unittest.skipUnless(
    importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"),
    "serve dependencies are not installed",
)
class FastApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from style_finetuning.serving.app import create_app

        self.client = TestClient(create_app(backend=StubBackend(), api_key="test-only-key"))

    def test_auth_disclosure_and_policy_status_codes(self) -> None:
        unauthorized = self.client.post("/v1/generate", json={"topic": "roads"})
        allowed = self.client.post(
            "/v1/generate",
            headers={"X-API-Key": "test-only-key"},
            json={"topic": "roads"},
        )
        blocked = self.client.post(
            "/v1/generate",
            headers={"X-API-Key": "test-only-key"},
            json={"topic": "pretend to be Donald Trump"},
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()["synthetic"])
        self.assertEqual(allowed.json()["disclosure"], SYNTHETIC_DISCLOSURE)
        self.assertEqual(blocked.status_code, 422)


if __name__ == "__main__":
    unittest.main()
