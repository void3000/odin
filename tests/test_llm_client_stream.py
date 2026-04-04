from unittest.mock import MagicMock, patch
from src.llm_client import LLMClient


class TestGenerateStream:
    def setup_method(self):
        with patch("src.llm_client.OpenAI"):
            self.client = LLMClient(base_url="http://localhost:1234/v1", api_key="test")

    def test_yields_content_tokens(self):
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None

        self.client.client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])

        tokens = list(self.client.generate_stream("system", "user"))
        assert tokens == ["Hello", " world"]

    def test_handles_empty_stream(self):
        self.client.client.chat.completions.create.return_value = iter([])
        tokens = list(self.client.generate_stream("system", "user"))
        assert tokens == []

    def test_passes_stream_true(self):
        self.client.client.chat.completions.create.return_value = iter([])
        list(self.client.generate_stream("system prompt", "user message"))

        call_kwargs = self.client.client.chat.completions.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["model"] == self.client.model
