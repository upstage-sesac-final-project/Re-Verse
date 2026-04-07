def extract_json(text: str) -> str:
    """LLM 출력에서 JSON 객체 추출."""
    if "```json" in text:
        s = text.index("```json") + 7
        e = text.index("```", s)
        return text[s:e].strip()
    if "```" in text:
        s = text.index("```") + 3
        e = text.index("```", s)
        return text[s:e].strip()
    s = text.find("{")
    e = text.rfind("}") + 1
    return text[s:e] if s >= 0 else text


def extract_yaml(text: str) -> str:
    """LLM 출력에서 YAML 추출."""
    if "```yaml" in text:
        s = text.index("```yaml") + 7
        e = text.index("```", s)
        return text[s:e].strip()
    if "```" in text:
        s = text.index("```") + 3
        e = text.index("```", s)
        return text[s:e].strip()
    if "events:" in text:
        return text[text.index("events:") :].strip()
    return text
