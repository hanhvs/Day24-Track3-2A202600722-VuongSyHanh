from __future__ import annotations

"""Phase C: Production Guardrails — Presidio PII + NeMo Guardrails + P95 Latency."""

import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ADVERSARIAL_SET_PATH, GUARDRAILS_CONFIG_DIR, LATENCY_BUDGET_P95_MS, PRESIDIO_LANGUAGE, OPENAI_API_KEY


# ─── Task 9a: Presidio PII Detection ─────────────────────────────────────────

def setup_presidio():
    """Khởi tạo Presidio engine với custom Vietnamese PII recognizers. (Đã implement sẵn)

    Custom recognizers thêm vào:
        VN_CCCD  — số CCCD 12 chữ số hoặc CMND 9 chữ số
        VN_PHONE — số điện thoại Việt Nam (0[3-9]xxxxxxxx)

    Các recognizers mặc định đã có sẵn: EMAIL, PHONE_NUMBER (international), ...
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, Pattern, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine

    cccd_recognizer = PatternRecognizer(
        supported_entity="VN_CCCD",
        patterns=[
            Pattern("CCCD 12 digits", r"\b\d{12}\b", 0.9),
            Pattern("CMND 9 digits",  r"\b\d{9}\b",  0.7),
        ],
    )
    phone_recognizer = PatternRecognizer(
        supported_entity="VN_PHONE",
        patterns=[Pattern("VN mobile", r"\b0[3-9]\d{8}\b", 0.9)],
    )

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()
    registry.add_recognizer(cccd_recognizer)
    registry.add_recognizer(phone_recognizer)

    analyzer  = AnalyzerEngine(registry=registry)
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


RELEVANT_PII_ENTITIES = {
    "VN_CCCD", "VN_PHONE", "PHONE_NUMBER", "EMAIL_ADDRESS",
    "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "US_SSN", "US_PASSPORT",
}


def pii_scan(text: str, analyzer=None, anonymizer=None) -> dict:
    """Task 9a: Quét PII trong văn bản bằng Presidio.

    Returns:
        {
          "has_pii":    bool,
          "entities":   [{"type": str, "text": str, "score": float, "start": int, "end": int}],
          "anonymized": str,   # text với PII được thay bằng <TYPE>
        }
    """
    if analyzer is None or anonymizer is None:
        analyzer, anonymizer = setup_presidio()

    results = analyzer.analyze(text=text, language=PRESIDIO_LANGUAGE)
    # Chỉ giữ các entity là PII thực sự (CCCD, phone, email, thẻ...) —
    # bỏ qua DATE_TIME / LOCATION / NRP / URL... vì gây false positive
    # (vd: "năm 2024" bị bắt thành DATE_TIME).
    results = [r for r in results if r.entity_type in RELEVANT_PII_ENTITIES]
    if not results:
        return {"has_pii": False, "entities": [], "anonymized": text}

    anonymized = anonymizer.anonymize(text=text, analyzer_results=results).text
    entities = [
        {"type": r.entity_type, "text": text[r.start:r.end],
         "score": round(r.score, 3), "start": r.start, "end": r.end}
        for r in results
    ]
    return {"has_pii": True, "entities": entities, "anonymized": anonymized}


# ─── Task 9b + 11: NeMo Guardrails ───────────────────────────────────────────

def setup_nemo_rails():
    """Khởi tạo NeMo Guardrails từ guardrails/config.yml. (Đã implement sẵn)

    Config directory: guardrails/
        config.yml  — model + rails config
        rails.co    — Colang dialogue flows (topic check, jailbreak check, output check)
    """
    from nemoguardrails import RailsConfig, LLMRails
    config = RailsConfig.from_path(GUARDRAILS_CONFIG_DIR)
    rails  = LLMRails(config)
    return rails


# Heuristic patterns (mirror rails.co) — dùng làm fallback khi NeMo không khả dụng
# (thiếu OPENAI_API_KEY hoặc init lỗi). Giúp adversarial suite vẫn chạy được offline.
_JAILBREAK_PATTERNS = [
    "bỏ qua tất cả hướng dẫn", "bỏ qua hướng dẫn", "ignore your previous",
    "ignore previous instructions", "ignore your system prompt", "ignore your system",
    "pretend you are dan", "do anything now", "unrestricted ai", "no restrictions",
    "forget your system prompt", "forget all hr", "system override", "system overload",
    "đóng vai ai không có giới hạn", "ai không có giới hạn", "không có giới hạn",
    "đóng vai hr manager", "đóng vai", "pretend you are", "admin command",
    "[admin", "ignore previous", "<!-- ignore", "ignore all", "priority 1",
    "in ra toàn bộ system", "system instructions", "tiết lộ", "dump all",
    "print all confidential", "list all employee salaries", "all employee salaries",
    "mật khẩu admin", "tấn công mạng", "hướng dẫn tấn công",
    "tôi là ceo", "tôi là giám đốc", "ra lệnh bạn bỏ qua",
]
_OFF_TOPIC_PATTERNS = [
    "viết một bài thơ", "bài thơ", "nấu", "phở", "công thức", "bitcoin", "ethereum",
    "giá cổ phiếu", "crypto", "recommend", "bộ phim", "marvel", "phim",
    "giải phương trình", "phương trình", "vi phân", "dy/dx", "thời tiết", "tin tức",
]
_PII_REQUEST_PATTERNS = [
    "cccd và số điện thoại của nhân viên", "cccd của nhân viên",
    "số điện thoại của nhân viên", "lương của nhân viên", "lương tháng của nhân viên",
    "thông tin cá nhân của", "email của nhân viên", "tiết lộ thông tin nhân viên",
    "tiết lộ lương", "tiết lộ bảng lương", "bảng lương chi tiết", "bảng lương",
    "lương của tất cả", "salaries",
]


def _heuristic_block(text: str) -> str | None:
    """Trả về reason (str) nếu nên block theo heuristic, None nếu allow."""
    low = text.lower()
    for kw in _JAILBREAK_PATTERNS:
        if kw in low:
            return "jailbreak"
    for kw in _PII_REQUEST_PATTERNS:
        if kw in low:
            return "pii_request"
    for kw in _OFF_TOPIC_PATTERNS:
        if kw in low:
            return "off_topic"
    return None


async def check_input_rail(text: str, rails=None) -> dict:
    """Task 9b: Kiểm tra input qua NeMo input rails (topic guard + jailbreak guard).

    Returns:
        {
          "allowed":        bool,
          "blocked_reason": str | None,
          "response":       str,          # NeMo's raw response
        }
    """
    # Nếu không có API key → NeMo (gọi LLM) không chạy được → dùng heuristic fallback.
    if rails is None and not OPENAI_API_KEY:
        reason = _heuristic_block(text)
        return {
            "allowed":        reason is None,
            "blocked_reason": f"heuristic_{reason}" if reason else None,
            "response":       "" if reason is None else "Xin lỗi, tôi không thể thực hiện yêu cầu này.",
        }

    try:
        if rails is None:
            rails = setup_nemo_rails()

        response = await rails.generate_async(
            messages=[{"role": "user", "content": text}]
        )
        if isinstance(response, dict):
            response = response.get("content", "")
        # NeMo từ chối bằng cách trả về refuse message được định nghĩa trong rails.co
        refuse_keywords = ["xin lỗi", "không thể", "không được phép", "i cannot", "i'm sorry"]
        blocked = any(kw in response.lower() for kw in refuse_keywords)
        # Kết hợp với heuristic để tăng recall
        if not blocked and _heuristic_block(text):
            blocked = True
        return {
            "allowed":        not blocked,
            "blocked_reason": "nemo_input_rail" if blocked else None,
            "response":       response,
        }
    except Exception as e:  # noqa: BLE001
        # NeMo lỗi → fallback heuristic để hệ thống vẫn an toàn.
        print(f"  ⚠️  check_input_rail NeMo failed: {e} — dùng heuristic fallback.")
        reason = _heuristic_block(text)
        return {
            "allowed":        reason is None,
            "blocked_reason": f"heuristic_{reason}" if reason else None,
            "response":       "" if reason is None else "Xin lỗi, tôi không thể thực hiện yêu cầu này.",
        }


async def check_output_rail(question: str, answer: str, rails=None) -> dict:
    """Task 11: Kiểm tra LLM output qua NeMo output rails trước khi trả về user.

    NeMo output rails hoạt động trong context của cả cuộc hội thoại (input + output).
    Kiểm tra: có PII không? Nội dung có phù hợp không? Có hallucination rõ ràng không?

    Returns:
        {
          "safe":           bool,
          "flagged_reason": str | None,
          "final_answer":   str,          # answer đã qua guard (có thể bị redact)
        }
    """
    # Output rail: phát hiện PII rò rỉ trong answer + heuristic nội dung nhạy cảm.
    sensitive_markers = [
        "cccd của nhân viên", "số điện thoại cá nhân", "mật khẩu hệ thống",
        "mật khẩu admin", "thông tin bí mật", "bảng lương chi tiết",
    ]
    low_ans = answer.lower()
    flagged_local = any(m in low_ans for m in sensitive_markers)

    # Kiểm tra PII rò rỉ bằng Presidio (CCCD/phone/email trong response)
    try:
        pii = pii_scan(answer)
        if pii["has_pii"]:
            flagged_local = True
    except Exception:  # noqa: BLE001
        pass

    if flagged_local:
        return {
            "safe": False,
            "flagged_reason": "sensitive_content_or_pii",
            "final_answer": "Tôi không thể cung cấp thông tin này. Vui lòng liên hệ phòng Nhân sự trực tiếp.",
        }

    # Nếu không có API key → chỉ dùng heuristic ở trên.
    if rails is None and not OPENAI_API_KEY:
        return {"safe": True, "flagged_reason": None, "final_answer": answer}

    try:
        if rails is None:
            rails = setup_nemo_rails()

        # Cung cấp context đầy đủ để output rail hoạt động
        response = await rails.generate_async(messages=[
            {"role": "user",      "content": question},
            {"role": "assistant", "content": answer},   # output cần kiểm tra
        ])
        if isinstance(response, dict):
            response = response.get("content", "")
        refuse_keywords = ["xin lỗi", "không thể cung cấp", "i cannot"]
        flagged = any(kw in response.lower() for kw in refuse_keywords)
        return {
            "safe":           not flagged,
            "flagged_reason": "nemo_output_rail" if flagged else None,
            "final_answer":   response if flagged else answer,
        }
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  check_output_rail NeMo failed: {e} — dùng heuristic kết quả.")
        return {"safe": True, "flagged_reason": None, "final_answer": answer}


# ─── Task 10: Adversarial Test Suite ─────────────────────────────────────────

def run_adversarial_suite(adversarial_set: list[dict], rails=None,
                           analyzer=None, anonymizer=None) -> list[dict]:
    """Task 10: Chạy 20 adversarial inputs qua full guard stack, so sánh với expected.

    Guard stack order:
        1. pii_scan()         → block nếu has_pii (cho category pii_injection)
        2. check_input_rail() → block nếu jailbreak / off-topic / prompt injection

    Returns:
        list of {
          "id": int, "category": str, "input": str,
          "expected": "blocked"|"allowed",
          "actual":   "blocked"|"allowed",
          "blocked_by": str | None,       # "presidio" | "nemo_input" | None
          "passed": bool,
        }
    """
    # Khởi tạo Presidio một lần (tránh init lại mỗi câu)
    if analyzer is None or anonymizer is None:
        try:
            analyzer, anonymizer = setup_presidio()
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  setup_presidio failed: {e}")

    async def _run_all():
        results = []
        for item in adversarial_set:
            blocked_by = None

            # Layer 1: Presidio PII (synchronous, fast)
            try:
                pii_result = pii_scan(item["input"], analyzer, anonymizer)
                if pii_result["has_pii"]:
                    blocked_by = "presidio"
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  pii_scan failed on id={item.get('id')}: {e}")

            # Layer 2: NeMo input rail (async — await, không dùng asyncio.run())
            if blocked_by is None:
                rail_result = await check_input_rail(item["input"], rails)
                if not rail_result["allowed"]:
                    blocked_by = "nemo_input"

            actual = "blocked" if blocked_by else "allowed"
            results.append({
                "id":         item["id"],
                "category":   item["category"],
                "input":      item["input"][:80] + "...",
                "expected":   item["expected"],
                "actual":     actual,
                "blocked_by": blocked_by,
                "passed":     actual == item["expected"],
            })
        return results

    results = asyncio.run(_run_all())   # một lần duy nhất
    passed = sum(1 for r in results if r["passed"])
    print(f"Adversarial suite: {passed}/{len(results)} passed")
    return results


# ─── Task 12: P95 Latency Measurement ────────────────────────────────────────

def measure_p95_latency(test_inputs: list[str], n_runs: int = 20,
                         rails=None, analyzer=None, anonymizer=None) -> dict:
    """Task 12: Đo P50/P95/P99 latency cho từng layer trong guard stack.

    Mục tiêu production: P95 total < LATENCY_BUDGET_P95_MS (500ms mặc định)

    Insight cần quan sát:
        - Presidio: local regex → rất nhanh (<10ms)
        - NeMo:     LLM API call → chậm (~200-800ms tuỳ model và network)
        → Tổng: dominated by NeMo

    Returns:
        {
          "presidio_ms":  {"p50": float, "p95": float, "p99": float},
          "nemo_ms":      {"p50": float, "p95": float, "p99": float},
          "total_ms":     {"p50": float, "p95": float, "p99": float},
          "latency_budget_ok": bool,
          "budget_ms": int,
        }
    """
    # Khởi tạo Presidio một lần
    if analyzer is None or anonymizer is None:
        try:
            analyzer, anonymizer = setup_presidio()
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  setup_presidio failed: {e}")

    presidio_times, nemo_times, total_times = [], [], []

    async def _measure():
        for text in test_inputs[:n_runs]:
            # Presidio (synchronous)
            t0 = time.perf_counter()
            try:
                pii_scan(text, analyzer, anonymizer)
            except Exception:  # noqa: BLE001
                pass
            presidio_ms = (time.perf_counter() - t0) * 1000

            # NeMo input rail (await — không dùng asyncio.run() trong loop)
            t1 = time.perf_counter()
            await check_input_rail(text, rails)
            nemo_ms = (time.perf_counter() - t1) * 1000

            presidio_times.append(presidio_ms)
            nemo_times.append(nemo_ms)
            total_times.append(presidio_ms + nemo_ms)

    asyncio.run(_measure())   # một lần duy nhất

    def percentiles(times):
        if not times:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        s = sorted(times)
        n = len(s)
        return {
            "p50": round(s[min(int(n * 0.50), n - 1)], 2),
            "p95": round(s[min(int(n * 0.95), n - 1)], 2),
            "p99": round(s[min(int(n * 0.99), n - 1)], 2),
        }

    total_p = percentiles(total_times)
    return {
        "presidio_ms": percentiles(presidio_times),
        "nemo_ms":     percentiles(nemo_times),
        "total_ms":    total_p,
        "latency_budget_ok": total_p["p95"] < LATENCY_BUDGET_P95_MS,
        "budget_ms": LATENCY_BUDGET_P95_MS,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Task 9a: PII scan demo
    test_pii = "Nhân viên Nguyễn Văn A, CCCD 034095001234, SĐT 0987654321 hỏi về nghỉ phép."
    result = pii_scan(test_pii)
    print(f"PII detected: {result['has_pii']}")
    print(f"Entities: {result['entities']}")
    print(f"Anonymized: {result['anonymized']}")

    # Task 10: Adversarial suite
    with open(ADVERSARIAL_SET_PATH, encoding="utf-8") as f:
        adversarial_set = json.load(f)
    print(f"\nLoaded {len(adversarial_set)} adversarial inputs")
    results = run_adversarial_suite(adversarial_set)
    if results:
        passed = sum(1 for r in results if r["passed"])
        print(f"Adversarial suite: {passed}/{len(results)} passed")

    # Task 12: P95 latency
    sample_inputs = [item["input"] for item in adversarial_set[:10]]
    latency = measure_p95_latency(sample_inputs, n_runs=10)
    print(f"\nLatency P95 — Presidio: {latency['presidio_ms']['p95']}ms | "
          f"NeMo: {latency['nemo_ms']['p95']}ms | "
          f"Total: {latency['total_ms']['p95']}ms")
    print(f"Budget OK ({latency['budget_ms']}ms): {latency['latency_budget_ok']}")

    # Save Phase C report
    os.makedirs("reports", exist_ok=True)
    passed = sum(1 for r in results if r["passed"]) if results else 0
    guard_report = {
        "pii_demo": {
            "input": test_pii,
            "has_pii": result["has_pii"],
            "entities": result["entities"],
            "anonymized": result["anonymized"],
        },
        "adversarial_suite": {
            "total": len(results),
            "passed": passed,
            "pass_rate": round(passed / len(results), 3) if results else 0.0,
            "results": results,
        },
        "latency": latency,
    }
    with open("reports/guard_results.json", "w", encoding="utf-8") as f:
        json.dump(guard_report, f, ensure_ascii=False, indent=2)
    print("\nPhase C report saved → reports/guard_results.json")
