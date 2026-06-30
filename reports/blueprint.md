# CI/CD Blueprint: RAG Eval + Guardrail Stack

**Sinh viên:** Vương Sỹ Hành (MSSV 2A202600722)
**Ngày:** Day 24 — Track 3

---

## Guard Stack Architecture

```
User Input
    │
    ▼ (~5ms P95)
[Presidio PII Scan]
    │ block if: VN_CCCD / VN_PHONE / EMAIL detected
    │ action:   return 400 + "PII detected in query"
    ▼ (~<1ms P95 heuristic, ~200-500ms khi dùng NeMo LLM)
[NeMo Input Rail]
    │ block if: off-topic / jailbreak / prompt injection
    │ action:   return 503 + refuse message
    ▼
[RAG Pipeline (Day 18)]
    │ M1 Chunk → M2 Search → M3 Rerank → GPT-4o-mini
    ▼
[NeMo Output Rail]
    │ flag if:  PII in response / sensitive content
    │ action:   replace with safe response
    ▼
User Response
```

Lưu ý triển khai: tầng NeMo Input/Output Rail có **fallback heuristic** (mirror các
flow trong `rails.co`) để hệ thống vẫn an toàn và đo được khi LLM API tạm thời không
khả dụng. Khi có `OPENAI_API_KEY`, rail sẽ gọi NeMo Guardrails (gpt-4o-mini) đầy đủ.

---

## Latency Budget

*(Điền từ kết quả Task 12 — measure_p95_latency(), n_runs=10)*

| Layer | P50 (ms) | P95 (ms) | P99 (ms) | Budget |
|---|---|---|---|---|
| Presidio PII | 4.03 | 5.13 | 5.13 | <10ms |
| NeMo Input Rail | 0.00 | 0.01 | 0.01 | <300ms |
| RAG Pipeline | ~ (Day 18) | ~ | ~ | <2000ms |
| NeMo Output Rail | ~ | ~ | ~ | <300ms |
| **Total Guard** | 4.04 | **5.14** | 5.14 | **<500ms** |

**Budget OK?** [x] Yes / [ ] No
**Comment:** Tầng Presidio (regex local) chiếm hầu hết latency (~5ms) nhưng vẫn rất nhỏ
so với budget. Ở chế độ heuristic, NeMo rail gần như tức thời. Khi bật NeMo LLM thật,
NeMo trở thành bottleneck (~200–500ms/call) — đây là layer cần tối ưu (cache, model nhỏ,
hoặc batch) nếu vượt budget trong production.

---

## CI/CD Gates (phải pass trước khi merge to main)

```yaml
# .github/workflows/rag_eval.yml
- name: RAGAS Quality Gate
  run: python src/phase_a_ragas.py
  env:
    MIN_FAITHFULNESS: 0.75
    MIN_AVG_SCORE: 0.65

- name: Guardrail Gate
  run: pytest tests/test_phase_c.py -k "test_adversarial_suite_pass_rate"
  # phải ≥ 15/20 (75%)  — thực tế đạt 20/20 (100%)

- name: Latency Gate
  run: python -c "from src.phase_c_guard import measure_p95_latency; ..."
  # P95 total < 500ms  — thực tế 5.14ms
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
| RAGAS avg_score (50q) | Cần `OPENAI_API_KEY` để chấm RAGAS (xem ghi chú dưới) |
| Worst metric | Cần RAGAS run |
| Dominant failure distribution | Cần RAGAS run |
| Cohen's κ | 0.00 (chế độ heuristic judge — cần LLM judge thật để đạt κ>0.6) |
| Adversarial pass rate | **20 / 20 (100%)** |
| Guard P95 latency | **5.14 ms** |

> Ghi chú: Phase B & C đã chạy thật và cho kết quả ở trên. Phase A (RAGAS) và Cohen's κ
> chất lượng cao cần một `OPENAI_API_KEY` hợp lệ (RAGAS dùng LLM để chấm faithfulness/
> relevancy; LLM-as-Judge cần gpt-4o-mini). Code đã sẵn sàng — chỉ cần điền key vào `.env`
> rồi chạy `python setup_answers.py && python src/phase_a_ragas.py && python src/phase_b_judge.py`.

---

## Nhận xét & Cải tiến

> Stack guardrail hoạt động rất tốt ở tầng phòng thủ đầu vào: Presidio bắt chính xác
> CCCD/CMND/SĐT/email tiếng Việt với latency cực thấp (~5ms), và tầng rail chặn 100%
> bộ 20 adversarial (jailbreak, prompt injection, off-topic, PII request). Điểm cần cải
> thiện nhất là tầng NeMo LLM khi bật thật: nó là bottleneck latency và phụ thuộc API
> bên ngoài — production nên thêm cache theo nội dung, circuit-breaker khi API timeout,
> và giữ heuristic làm lớp phòng thủ dự phòng. Nếu deploy thật, tôi sẽ (1) chuyển từ
> hard-coded keyword sang một classifier nhỏ fine-tuned cho jailbreak/off-topic để giảm
> brittleness, (2) thêm rate-limit + audit log cho mọi lần PII bị chặn, và (3) đưa
> RAGAS faithfulness vào CI gate chạy nightly trên sample thật để bắt regression sớm.
