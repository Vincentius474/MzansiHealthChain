from app import llm


def test_deidentify_scrubs_identifiers():
    text = ("Patient 8001015009087 mail jo@example.com phone 0821234567 "
            "wallet 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
    out = llm.deidentify(text)
    for leaked in ("8001015009087", "jo@example.com", "0821234567", "0xf39F"):
        assert leaked not in out
    for tag in ("[ID]", "[EMAIL]", "[PHONE]", "[WALLET]"):
        assert tag in out


def test_deidentify_leaves_clinical_text_alone():
    s = "Type 2 diabetes, metformin 500mg twice daily."
    assert llm.deidentify(s) == s


async def test_sensitive_prompts_only_go_to_ollama(monkeypatch):
    calls = []

    async def ollama(p): calls.append("ollama"); return "ok"
    async def groq(p): calls.append("groq"); return "ok"
    async def gemini(p): calls.append("gemini"); return "ok"

    monkeypatch.setattr(llm, "_ollama", ollama)
    monkeypatch.setattr(llm, "_groq", groq)
    monkeypatch.setattr(llm, "_gemini", gemini)
    monkeypatch.setattr(llm.settings, "groq_api_key", "k")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "k")

    _, model = await llm.complete("anything", sensitive=True, complexity="complex")
    assert model == "ollama" and calls == ["ollama"]


async def test_cloud_models_receive_deidentified_text(monkeypatch):
    seen = {}

    async def groq(p): seen["prompt"] = p; return "ok"

    monkeypatch.setattr(llm, "_groq", groq)
    monkeypatch.setattr(llm.settings, "groq_api_key", "k")
    _, model = await llm.complete("email jo@example.com", sensitive=False)
    assert model == "groq" and "jo@example.com" not in seen["prompt"]
