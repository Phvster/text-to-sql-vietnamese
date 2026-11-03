"""app.py — logic demo (không cần gradio, không gọi API): FakeLLM + DB thật."""
from __future__ import annotations

import pytest

import app
from src.db.executor import execute
from src.pipeline.llm import FakeLLM

Q = "Có bao nhiêu khách hàng VIP?"
SQL = "SELECT COUNT(*) FROM customers WHERE segment = 'vip'"


def _llm(answer: dict, tables: list[str] | None = None) -> FakeLLM:
    return FakeLLM({Q: answer}, table_answers={Q: {"tables": tables or ["customers"]}})


def test_c3_returns_sql_rows_tables_and_dev_shots() -> None:
    result = app.ask(Q, "C3", llm=_llm({"refuse": False, "sql": SQL}))
    assert result.sql == SQL and result.columns and len(result.rows) == 1
    assert result.rows == execute(SQL).rows
    assert result.tables == ["customers"]
    assert len(result.shots) == 3 and all(s.startswith("dev-") for s in result.shots)


def test_c0_has_no_linking_and_no_examples() -> None:
    llm = _llm({"refuse": False, "sql": SQL})
    result = app.ask(Q, "C0", llm=llm)
    assert result.tables is None and result.shots == [] and len(llm.calls) == 1


def test_refusal_is_shown_and_nothing_runs() -> None:
    result = app.ask(Q, "C0", llm=_llm({"refuse": True, "sql": ""}))
    assert "từ chối" in result.message and result.rows == [] and result.sql == ""


def test_write_sql_is_blocked_by_executor() -> None:
    before = execute("SELECT COUNT(*) FROM reviews").rows
    result = app.ask(Q, "C0", llm=_llm({"refuse": False, "sql": "DELETE FROM reviews"}))
    assert result.message.startswith("SQL bị từ chối") and result.rows == []
    assert execute("SELECT COUNT(*) FROM reviews").rows == before


@pytest.mark.parametrize("question", ["", "   ", "x" * (app.MAX_QUESTION_CHARS + 1)])
def test_empty_or_too_long_question_never_calls_llm(question: str) -> None:
    llm = _llm({"refuse": False, "sql": SQL})
    assert app.ask(question, "C3", llm=llm).message and llm.calls == []


def test_invalid_config_or_model_rejected() -> None:
    llm = _llm({"refuse": False, "sql": SQL})
    assert app.ask(Q, "C9", llm=llm).message and app.ask(Q, "C0", "gpt", llm=llm).message and llm.calls == []


def test_dev_question_typed_verbatim_is_left_out_of_its_own_examples() -> None:
    dev = app.load_pool()[0]
    llm = FakeLLM({dev["question"]: {"refuse": False, "sql": SQL}},
                  table_answers={dev["question"]: {"tables": ["customers"]}})
    result = app.ask(dev["question"], "C3", llm=llm)
    assert dev["id"] not in result.shots and len(result.shots) == 3  # leave-one-out như lúc đánh giá


class _Raising:
    name = "raising"

    def complete(self, *_a, **_k):
        raise TypeError("Could not resolve authentication method")


def test_llm_exception_becomes_message_not_crash() -> None:
    result = app.ask(Q, "C2", llm=_Raising())
    assert "ANTHROPIC_API_KEY" in result.message and result.rows == []


def test_transient_api_error_shown_and_nothing_runs() -> None:
    result = app.ask(Q, "C0", llm=FakeLLM({}))  # FakeLLM không có câu trả lời → LLMReply.error
    assert result.message.startswith("Lỗi API") and result.rows == []


def test_c4_refusal_during_repair_shows_first_sql() -> None:
    empty = "SELECT customer_id FROM customers WHERE 1 = 0"
    llm = _llm([{"refuse": False, "sql": empty}, {"refuse": True, "sql": ""}])
    result = app.ask(Q, "C4", llm=llm)
    assert result.sql == empty and "lượt sửa" in result.message and result.rows == []


def test_truncated_result_is_flagged() -> None:
    result = app.ask(Q, "C0", llm=_llm({"refuse": False, "sql": "SELECT order_id FROM orders"}))
    assert len(result.rows) == 1000 and "đã cắt" in result.message


def test_examples_come_from_dev_only() -> None:
    pool = app.load_pool()
    examples = app.demo_examples()
    dev_questions = {q["question"] for q in pool}
    assert len(examples) == app.N_EXAMPLES and set(examples) <= dev_questions
    assert all(q["id"].startswith("dev-") for q in pool)
