from dataclasses import dataclass


FACTUAL_EXTRACTION_SYSTEM_PROMPT = """You are a factual claim extraction engine.
Extract only verifiable claims, and include direct evidence spans.
Return JSON only, strictly following the schema contract.
"""


CLAIM_SCHEMA_CONTRACT = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string"},
                    "claim_type": {
                        "type": "string",
                        "enum": [
                            "observed_fact",
                            "attributed_statement",
                            "inference",
                            "prediction",
                            "opinion",
                        ],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                    },
                },
                "required": ["claim_text", "claim_type", "evidence"],
            },
        }
    },
    "required": ["claims"],
}


@dataclass
class ExtractionPrompt:
    system_prompt: str
    user_prompt: str


def build_claim_extraction_prompt(source_name: str, title: str, cleaned_text: str) -> ExtractionPrompt:
    user_prompt = (
        f"Source: {source_name}\n"
        f"Title: {title}\n\n"
        "Article text:\n"
        f"{cleaned_text}\n\n"
        "Extract factual claims following the schema contract."
    )
    return ExtractionPrompt(system_prompt=FACTUAL_EXTRACTION_SYSTEM_PROMPT, user_prompt=user_prompt)
