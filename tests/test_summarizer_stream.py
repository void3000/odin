from unittest.mock import MagicMock
from src.summarizer import ResultSummarizer


class TestSummarizeStream:
    def test_yields_tokens_from_llm(self):
        mock_llm = MagicMock()
        mock_llm.generate_stream.return_value = iter(["Found ", "3 ", "artists."])

        summarizer = ResultSummarizer(mock_llm)
        tokens = list(summarizer.summarize_stream(
            question="show artists",
            results=[{"name": "AC/DC"}, {"name": "Metallica"}, {"name": "Nirvana"}],
            sql="SELECT name FROM artist",
        ))

        assert tokens == ["Found ", "3 ", "artists."]
        mock_llm.generate_stream.assert_called_once()

    def test_passes_correct_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate_stream.return_value = iter(["ok"])

        summarizer = ResultSummarizer(mock_llm)
        list(summarizer.summarize_stream(
            question="show artists",
            results=[{"name": "AC/DC"}],
            sql="SELECT name FROM artist",
        ))

        call_args = mock_llm.generate_stream.call_args
        system_prompt = call_args[0][0]
        user_message = call_args[0][1]
        assert "data analyst" in system_prompt.lower()
        assert "show artists" in user_message
        assert "AC/DC" in user_message
