# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Vương Sỹ Hành (MSSV 2A202600722)
**Ngày:** Day 24 — Track 3
**LLM:** openai/gpt-4o-mini (qua OpenRouter) · RAGAS embeddings: local (multilingual MiniLM)

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~6ms P95)
[Presidio PII Scan]
    │ block if: VN_CCCD / VN_PHONE / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~54ms P95 — NeMo Guardrails LLM)
[NeMo Input Rail]
    │ block if: off-topic / jailbreak / prompt injection
    │ action:   return 503 + refuse message
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 Hybrid Search → M3 Rerank → gpt-4o-mini
    ▼
[NeMo Output Rail]
    │ flag if:  PII in response / sensitive content
    │ action:   replace with safe response
    ▼
User Response
```

Tầng NeMo Input/Output Rail có thêm **fallback heuristic** (mirror các flow trong
`rails.co`) để hệ thống vẫn an toàn khi LLM API tạm thời lỗi/timeout.

---

## Latency Budget

*(Đo thật bằng Task 12 — measure_p95_latency(), n_runs=10, qua OpenRouter)*

| Layer | P50 (ms) | P95 (ms) | P99 (ms) | Budget |
|---|---|---|---|---|
| Presidio PII | 5.x | 6.16 | 6.16 | <10ms |
| NeMo Input Rail | ~50 | 53.94 | 53.94 | <300ms |
| RAG Pipeline | ~ (Day 18) | ~ | ~ | <2000ms |
| NeMo Output Rail | ~50 | ~54 | ~54 | <300ms |
| **Total Guard (Presidio+NeMo input)** | 55.54 | **59.52** | 59.52 | **<500ms** |

**Budget OK?** [x] Yes / [ ] No
**Comment:** Tổng P95 guard = **59.52ms**, dưới xa budget 500ms. Presidio (regex local)
chỉ ~6ms; NeMo rail (~54ms) là layer chậm hơn vì có gọi LLM nhưng vẫn rất nhanh nhờ
gpt-4o-mini. Nếu scale, NeMo là bottleneck cần theo dõi đầu tiên (cache + circuit-breaker).

---

## CI/CD Gates (phải pass trước khi merge to main)

```yaml
# .github/workflows/rag_eval.yml
- name: RAGAS Quality Gate
  run: python src/phase_a_ragas.py
  env:
    MIN_FAITHFULNESS: 0.75   # factual faithfulness thực tế = 0.958 ✓
    MIN_AVG_SCORE: 0.65      # factual 0.909 / multi_hop 0.695 / adversarial 0.815 ✓

- name: Guardrail Gate
  run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
  # yêu cầu ≥ 15/20 (75%) — thực tế 20/20 (100%) ✓

- name: Latency Gate
  run: python -c "from src.phase_c_guard import measure_p95_latency; ..."
  # P95 total < 500ms — thực tế 59.52ms ✓
```

---

## Monitoring Dashboard (production)

| Metric | Alert Threshold | Action |
|---|---|---|
| RAGAS faithfulness (daily sample) | < 0.70 | Page on-call |
| Adversarial block rate | < 80% | Review new attack patterns |
| Guard P95 latency | > 600ms | Scale NeMo model |
| PII detected count | spike >10/hour | Security alert |

---

## Kết quả thực tế từ Lab

| | Kết quả |
|---|---|
| RAGAS avg_score (50q) | factual **0.909** · multi_hop **0.695** · adversarial **0.815** |
| Worst metric (theo count) | answer_relevancy (23 câu), kế đến faithfulness (14 câu) |
| Dominant failure distribution | multi_hop (theo avg_score thấp nhất 0.695) |
| Cohen's κ | **1.00** (almost perfect, 10/10) — **bonus đạt** |
| Adversarial pass rate | **20 / 20 (100%)** — **bonus đạt** (≥18/20) |
| Guard P95 latency | **59.52 ms** |

**Bonus đạt cả 3:** Phase A (adversarial 0.815 < factual 0.909) ✓ · Phase B (κ=1.0 > 0.6) ✓ · Phase C (20/20 ≥ 18/20) ✓

---

## Nhận xét & Cải tiến

> Stack hoạt động rất tốt end-to-end: Presidio bắt chính xác CCCD/CMND/SĐT/email tiếng Việt
> ở ~6ms; NeMo rail + heuristic chặn 100% bộ 20 adversarial (jailbreak, prompt injection,
> off-topic, PII request) ở ~54ms; tổng guard P95 chỉ 59ms — thừa sức cho budget 500ms.
> Về chất lượng RAG: faithfulness factual 0.958 cho thấy pipeline không bịa với câu thẳng,
> nhưng multi_hop (0.483 faithfulness) lộ điểm yếu khi phải tính toán — đây là ưu tiên cải
> thiện số 1. LLM-as-Judge gpt-4o-mini đạt κ=1.0 với human, đủ tin cậy để đưa vào CI gate.
> Nếu deploy thật, tôi sẽ: (1) thêm version-aware retrieval để xử lý version conflicts
> (v2023/v2024) tốt hơn — nguồn lỗi chính của context_recall ở adversarial; (2) tách bước
> tính toán số (lương/phụ cấp/phí phạt) ra prompt riêng + temperature=0 để nâng faithfulness
> multi_hop; (3) thêm cache + circuit-breaker cho NeMo rail và giữ heuristic làm lớp dự phòng;
> (4) chạy RAGAS nightly trên sample thật để bắt regression sớm.
