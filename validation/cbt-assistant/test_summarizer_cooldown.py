import httpx
import pytest

from src.memory.summarizer import MemorySummarizer
from src.utils.db import SQLiteSessionManager


class ScriptedLLM:
    """Raises a real httpx timeout while `failing` is True, then answers."""

    def __init__(self):
        self.failing = True
        self.calls = 0

    async def chat(self, *args, **kwargs):
        self.calls += 1
        if self.failing:
            raise httpx.ReadTimeout("model did not answer in time")
        return {"content": "Resumo: usuária tem uma cachorra chamada Rex."}


def make(tmp_path, session="s1"):
    db = SQLiteSessionManager(tmp_path / "memory.db")
    for i in range(4):
        db.add_message(session, "user" if i % 2 == 0 else "assistant", f"mensagem {i}")
    llm = ScriptedLLM()
    summarizer = MemorySummarizer(db, llm)
    summarizer.trigger_threshold = 2
    summarizer.retry_cooldown_s = 300.0
    now = [1000.0]
    summarizer._clock = lambda: now[0]
    return db, llm, summarizer, now


@pytest.mark.asyncio
async def test_failure_blocks_model_calls_during_cooldown(tmp_path):
    db, llm, summarizer, now = make(tmp_path)
    await summarizer._process_summarization("s1")  # fails, starts cooldown
    assert llm.calls == 1

    now[0] += 60  # still inside the 300 s window
    await summarizer._process_summarization("s1")
    await summarizer._process_summarization("s1")
    assert llm.calls == 1, "model was called again during cooldown"
    assert len(db.get_unsummarized_messages("s1")) == 4  # still pending


@pytest.mark.asyncio
async def test_retry_after_cooldown_saves_summary(tmp_path):
    db, llm, summarizer, now = make(tmp_path)
    await summarizer._process_summarization("s1")  # fails
    llm.failing = False
    now[0] += 301  # window elapsed
    await summarizer._process_summarization("s1")
    assert llm.calls == 2
    assert "Rex" in db.get_session_summary("s1")
    assert db.get_unsummarized_messages("s1") == []


@pytest.mark.asyncio
async def test_cooldown_is_per_session(tmp_path):
    db, llm, summarizer, now = make(tmp_path, session="s1")
    for i in range(4):
        db.add_message("s2", "user" if i % 2 == 0 else "assistant", f"outra {i}")
    await summarizer._process_summarization("s1")  # s1 fails, s1 cools down
    await summarizer._process_summarization("s2")  # s2 must still be attempted
    assert llm.calls == 2
