import httpx
import pytest

from src.memory.summarizer import MemorySummarizer
from src.utils.db import SQLiteSessionManager


class FlakyLLM:
    """Fails for the first `failures` calls, then answers normally."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    async def chat(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.ReadTimeout("model did not answer in time")
        return {"content": "Resumo: usuária tem uma cachorra chamada Rex."}


@pytest.mark.asyncio
async def test_failed_summary_keeps_messages_and_retry_saves(tmp_path):
    db = SQLiteSessionManager(tmp_path / "memory.db")
    for i in range(4):
        db.add_message("s1", "user" if i % 2 == 0 else "assistant", f"mensagem {i}")

    llm = FlakyLLM(failures=1)
    summarizer = MemorySummarizer(db, llm)
    summarizer.trigger_threshold = 2

    # First attempt fails: nothing saved, messages still pending.
    await summarizer._process_summarization("s1")
    assert db.get_session_summary("s1") == ""
    assert len(db.get_unsummarized_messages("s1")) == 4

    # Next trigger succeeds: summary saved and the messages are marked done.
    await summarizer._process_summarization("s1")
    assert "Rex" in db.get_session_summary("s1")
    assert db.get_unsummarized_messages("s1") == []
    assert llm.calls == 2
