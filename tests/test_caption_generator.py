from caption_generator import build_prompt, generate_caption
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_build_prompt_includes_price_and_ingredients(monkeypatch):
    menu = {
        "name": "นมหมีฮอกไกโด",
        "price": 65,
        "size": "350 ml",
        "ingredients": ["นมสดฮอกไกโด", "วิปครีม"],
    }

    prompt = build_prompt(menu)

    assert "65 บาท" in prompt
    assert "350 ml" in prompt
    assert "นมสดฮอกไกโด" in prompt
    assert "วิปครีม" in prompt


def test_generate_caption_uses_menu_data(monkeypatch):
    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key

        class models:
            @staticmethod
            def generate_content(model, contents):
                class Response:
                    text = "caption"

                return Response()

    import caption_generator as module

    monkeypatch.setattr(module, "genai", type(
        "GenAI", (), {"Client": FakeClient}))
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    caption = generate_caption({"name": "นมหมีฮอกไกโด", "price": 65})
    assert caption == "caption"


def test_generate_caption_retries_when_output_is_too_long(monkeypatch):
    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key

        class models:
            call_count = 0

            @classmethod
            def generate_content(cls, model, contents):
                class Response:
                    def __init__(self, text):
                        self.text = text

                cls.call_count += 1
                if cls.call_count < 3:
                    return Response("x" * 300)
                return Response("short caption")

    import caption_generator as module

    monkeypatch.setattr(module, "genai", type(
        "GenAI", (), {"Client": FakeClient}))
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    caption = generate_caption({"name": "นมหมีฮอกไกโด", "price": 65})
    assert caption == "short caption"
