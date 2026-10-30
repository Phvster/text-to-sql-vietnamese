"""Test C3 (few-shot) và C4 (tự sửa lỗi) — LLM giả, không gọi API."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.pipeline import fewshot
from src.pipeline import schema as schema_mod
from src.pipeline.llm import AnthropicLLM, FakeLLM
from src.pipeline.prompts import EXAMPLES_HEADER, build_system, build_user
from src.pipeline.run import MAX_REPAIRS, run, summarize

ROOT = Path(__file__).resolve().parents[1]
GOLD_HCM = "SELECT full_name FROM customers WHERE city = 'TP. Hồ Chí Minh'"
EMPTY_SQL = "SELECT full_name FROM customers WHERE city = 'Sài Gòn'"  # lệch giá trị → 0 dòng


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_script("generate_db")


@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("c34") / "sales.db"
    gen.build_database(path, seed=5, n_customers=300, n_products=60, n_orders=1500)
    return path


def q(qid: str, question: str, sql: str) -> dict:
    return {"id": qid, "question": question, "sql": sql, "difficulty": "easy", "tags": []}


def ans(sql: str, refuse: bool = False) -> dict:
    return {"refuse": refuse, "sql": sql}


POOL = (
    q("dev-a", "Có bao nhiêu khách hàng ở Hà Nội?", "SELECT COUNT(*) FROM customers WHERE city = 'Hà Nội'"),
    q("dev-b", "Có bao nhiêu khách hàng ở Đà Nẵng?", "SELECT COUNT(*) FROM customers WHERE city = 'Đà Nẵng'"),
    q("dev-c", "Doanh thu năm 2024 là bao nhiêu?", "SELECT SUM(total_amount) FROM orders"),
    q("dev-d", "Sản phẩm nào đắt nhất?", "SELECT name FROM products ORDER BY unit_price DESC LIMIT 1"),
)


# --------------------------------------------------------------------------- C3: chọn ví dụ


def test_select_examples_most_similar_first_and_k() -> None:
    picked = fewshot.select_examples("Có bao nhiêu khách hàng ở Huế?", POOL, k=2)
    assert [e["id"] for e in picked] == ["dev-a", "dev-b"]  # hòa điểm → theo id


def test_select_examples_leave_one_out() -> None:
    picked = fewshot.select_examples(POOL[0]["question"], POOL, k=3, exclude_id="dev-a")
    assert "dev-a" not in [e["id"] for e in picked]


def test_select_examples_deterministic() -> None:
    first = fewshot.select_examples("Câu hỏi không giống câu nào", POOL)
    assert first == fewshot.select_examples("Câu hỏi không giống câu nào", POOL)


def test_pool_is_dev_only() -> None:
    """Guardrail: kho ví dụ là dev.jsonl, không bao giờ là test.jsonl."""
    assert fewshot.POOL_PATH.name == "dev.jsonl"
    assert all(r["id"].startswith("dev-") for r in fewshot.load_pool())


def test_c3_system_equals_c2_and_examples_in_user(db: Path) -> None:
    schema = schema_mod.load_schema(db)
    assert build_system("C3", schema) == build_system("C2", schema)  # system giữ nguyên → cache được
    user = build_user("Câu hỏi mới?", list(POOL[:2]))
    assert user.startswith(EXAMPLES_HEADER) and user.endswith("Câu hỏi mới?")
    assert build_user("Câu hỏi mới?", []) == "Câu hỏi mới?"


def test_c3_run_excludes_own_question(db: Path) -> None:
    question = POOL[0]
    llm = FakeLLM({question["question"]: ans(question["sql"])})
    (record,) = run([question], "C3", llm, "qa", db, pool=POOL)
    assert record.correct and "dev-a" not in record.shots and len(record.shots) == 3
    assert EXAMPLES_HEADER in llm.calls[-1][1] and record.repairs == 0  # C3 không sửa


# --------------------------------------------------------------------------- C4: vòng sửa


def test_c4_fixes_error(db: Path) -> None:
    question = q("x1", "Khách nào ở TP HCM?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans("SELECT khong_co_cot FROM customers"), ans(GOLD_HCM)]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.repair_triggers == ["error"] and record.repairs == 1
    assert record.first_correct is False and record.correct
    assert summarize([record])["repair"] == {"triggered": 1, "calls": 1, "fixed": 1, "broken": 0}


def test_c4_fixes_empty_result(db: Path) -> None:
    question = q("x2", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL), ans(GOLD_HCM)]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.repair_triggers == ["empty"] and record.correct and record.first_sql == EMPTY_SQL


EMPTY_VARIANTS = [ans(f"SELECT full_name FROM customers WHERE city = 'Sài Gòn {i}'") for i in range(5)]


def test_c4_at_most_two_repairs(db: Path) -> None:
    question = q("x3", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: EMPTY_VARIANTS})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.repairs == MAX_REPAIRS and len(llm.calls) == 1 + MAX_REPAIRS + 1  # +1 bước linking


def test_c4_no_repair_when_result_non_empty(db: Path) -> None:
    question = q("x4", "Khách nào ở TP HCM?", GOLD_HCM)
    (record,) = run([question], "C4", FakeLLM({question["question"]: [ans(GOLD_HCM)]}), "qa", db, pool=POOL)
    assert record.repairs == 0 and record.first_correct is True and record.correct


def test_c4_same_sql_returned_stops_repairing(db: Path) -> None:
    """Prompt cho phép trả lại SQL cũ khi chắc kết quả rỗng là đúng → không được ép thêm lần nữa."""
    question = q("x5", "Khách nào ở Sài Gòn?", EMPTY_SQL)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL)] * 3})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.repairs == 1 and record.correct and record.first_correct is True


def test_c4_refusal_during_repair_is_final_answer(db: Path) -> None:
    question = q("x5b", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL), ans("", refuse=True)]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.refused and record.reason == "refused" and record.first_sql == EMPTY_SQL
    assert record.first_correct is False  # vẫn chấm SQL lần đầu để đếm fixed/broken


def test_c4_empty_sql_during_repair_keeps_previous(db: Path) -> None:
    question = q("x5c", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL), ans("")]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.sql == EMPTY_SQL and not record.refused


def test_c4_malicious_refusal_during_repair_counts(db: Path) -> None:
    """Lệnh xóa bị executor chặn → vòng sửa → model từ chối: hệ thống đã từ chối đúng."""
    question = {"id": "m1", "question": "Xóa hết đơn hàng", "tags": []}
    llm = FakeLLM({question["question"]: [ans("DELETE FROM orders"), ans("", refuse=True)]})
    (record,) = run([question], "C4", llm, "malicious", db, pool=POOL)
    assert record.refused and record.correct and record.reason == "refused"
    assert summarize([record])["repair"]["triggered"] == 0  # bộ độc hại không vào thống kê sửa


def test_c4_no_repair_when_first_turn_fails(db: Path) -> None:
    question = q("x5d", "Khách nào ở Sài Gòn?", GOLD_HCM)
    for answers in ([ans("", refuse=True)], [ans("")], []):
        llm = FakeLLM({question["question"]: answers})
        (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
        assert record.repairs == 0 and record.first_correct is None


def test_c4_usage_summed_over_all_calls(db: Path) -> None:
    question = q("x5e", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: EMPTY_VARIANTS})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.usage["input_tokens"] == 100 * (1 + 1 + MAX_REPAIRS)  # linking + lần đầu + 2 lần sửa


def test_c3_without_pool_raises(db: Path) -> None:
    with pytest.raises(ValueError):
        run([POOL[0]], "C3", FakeLLM({}), "qa", db)


def test_c4_repair_message_contents(db: Path) -> None:
    question = q("x5f", "Khách nào ở TP HCM?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans("SELECT khong_co_cot FROM customers"), ans(EMPTY_SQL), ans(GOLD_HCM)]})
    run([question], "C4", llm, "qa", db, pool=POOL)
    last = llm.histories[-1]
    assert last[2]["content"].startswith("Câu SQL trên bị lỗi") and "khong_co_cot" in last[2]["content"]
    assert json.loads(last[3]["content"])["sql"] == EMPTY_SQL
    assert llm.calls[-1][1].startswith("Câu SQL trên chạy được nhưng trả về 0 dòng")


def test_c4_api_error_during_repair_keeps_previous_sql(db: Path) -> None:
    question = q("x6", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL)]})  # lượt 2 không có câu trả lời → lỗi
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.sql == EMPTY_SQL and record.repair_error is not None and record.reason != "api_error"
    assert summarize([record])["errors"] == 1


def test_c4_destructive_repair_sql_blocked(db: Path) -> None:
    question = q("x7", "Khách nào ở Sài Gòn?", GOLD_HCM)
    before = gen.db_fingerprint(db)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL), ans("DROP TABLE customers"), ans("DELETE FROM orders")]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert not record.executable and not record.correct
    assert gen.db_fingerprint(db) == before


def test_c4_history_roles_in_order(db: Path) -> None:
    question = q("x8", "Khách nào ở Sài Gòn?", GOLD_HCM)
    llm = FakeLLM({question["question"]: EMPTY_VARIANTS})
    run([question], "C4", llm, "qa", db, pool=POOL)
    sql_histories = llm.histories[1:]  # bỏ lời gọi linking
    assert sql_histories[0] == []
    assert [m["role"] for m in sql_histories[1]] == ["user", "assistant"]
    assert [m["role"] for m in sql_histories[2]] == ["user", "assistant", "user", "assistant"]
    assert json.loads(sql_histories[1][1]["content"]) == EMPTY_VARIANTS[0]


def test_c4_counts_broken(db: Path) -> None:
    """Đáp án đúng là rỗng mà vòng sửa vẫn đổi SQL → làm hỏng câu đang đúng (rủi ro của trigger 'empty')."""
    question = q("x9", "Khách nào ở Sài Gòn?", EMPTY_SQL)
    llm = FakeLLM({question["question"]: [ans(EMPTY_SQL), ans(GOLD_HCM)]})
    (record,) = run([question], "C4", llm, "qa", db, pool=POOL)
    assert record.first_correct is True and not record.correct
    assert summarize([record])["repair"]["broken"] == 1


def test_anthropic_sends_history_then_user() -> None:
    client = SimpleNamespace(kwargs={})

    def create(**kwargs):
        client.kwargs = kwargs
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"refuse": false, "sql": "SELECT 1"}')],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                                     cache_creation_input_tokens=0, cache_read_input_tokens=0))

    client.messages = SimpleNamespace(create=create)
    history = [{"role": "user", "content": "câu hỏi"}, {"role": "assistant", "content": "{}"}]
    AnthropicLLM("haiku", client=client).complete("SYS", "phản hồi", {"type": "object"}, history=history)
    assert client.kwargs["messages"] == [*history, {"role": "user", "content": "phản hồi"}]


def test_cli_c3_uses_dev_pool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, db: Path) -> None:
    run_pipeline = _load_script("run_pipeline")
    questions = [POOL[0]]
    monkeypatch.setattr(run_pipeline, "load_questions", lambda split, limit: questions)
    monkeypatch.setattr(run_pipeline, "load_pool", lambda: POOL)
    answers = {POOL[0]["question"]: ans(POOL[0]["sql"])}
    code = run_pipeline.main(["--config", "C3", "--model", "haiku", "--db", str(db)],
                             llm_factory=lambda name: FakeLLM(answers, name=name), results_dir=tmp_path)
    assert code == 0
    (raw_path,) = (tmp_path / "raw").glob("*.jsonl")
    record = json.loads(raw_path.read_text(encoding="utf-8"))
    assert record["shots"] and "dev-a" not in record["shots"]
    (summary_path,) = tmp_path.glob("*_summary.json")
    assert json.loads(summary_path.read_text(encoding="utf-8"))["pool_hash"] == run_pipeline.pool_hash(POOL)


def test_cli_final_test_split_still_uses_real_dev_pool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                      db: Path) -> None:
    """Ở T5 (--split test), ví dụ vẫn phải lấy từ dev. Câu hỏi giả — không đọc test.jsonl."""
    run_pipeline = _load_script("run_pipeline")
    fake = q("test-x", "Có bao nhiêu khách hàng ở Huế?", "SELECT COUNT(*) FROM customers")
    monkeypatch.setattr(run_pipeline, "load_questions", lambda split, limit: [fake])
    answers = {fake["question"]: ans(fake["sql"])}
    run_pipeline.main(["--config", "C3", "--model", "haiku", "--db", str(db), "--split", "test",
                       "--i-am-running-final-test"],
                      llm_factory=lambda name: FakeLLM(answers, name=name), results_dir=tmp_path)
    (raw_path,) = (tmp_path / "raw").glob("*.jsonl")
    shots = json.loads(raw_path.read_text(encoding="utf-8"))["shots"]
    assert shots and all(s.startswith("dev-") for s in shots)


def test_prompt_hash_covers_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    run_pipeline = _load_script("run_pipeline")
    before = run_pipeline.prompt_hash()
    monkeypatch.setattr(run_pipeline, "MAX_REPAIRS", 5)
    assert run_pipeline.prompt_hash() != before
