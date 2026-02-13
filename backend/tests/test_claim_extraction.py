import json

import pytest

from app.services.claim_extraction import parse_claim_extraction_json


def test_parse_claim_extraction_json_valid_payload():
    payload = {
        "claims": [
            {
                "claim_text": "OpenAI released a new model.",
                "claim_type": "observed_fact",
                "confidence": 0.91,
                "evidence": [
                    {
                        "evidence_text": "OpenAI released a new model today.",
                        "evidence_type": "reported_fact",
                    }
                ],
            }
        ]
    }

    result = parse_claim_extraction_json(json.dumps(payload))

    assert len(result.claims) == 1
    assert result.claims[0].claim_type == "observed_fact"


def test_parse_claim_extraction_json_invalid_payload_raises():
    invalid_payload = {"claims": [{"claim_type": "observed_fact", "evidence": []}]}

    with pytest.raises(ValueError):
        parse_claim_extraction_json(json.dumps(invalid_payload))
