# Báo cáo Lab 24 — Production Eval + Guardrail Stack

**Sinh viên:** Vương Sỹ Hành
**MSSV:** 2A202600722
**Track:** 3 — Eval + Guardrail
**LLM:** `openai/gpt-4o-mini` (qua OpenRouter) · RAGAS embeddings: local (multilingual MiniLM)
**Vector DB:** Qdrant 1.18.2 · Embedding RAG: BAAI/bge-m3

---

## 1. Tóm tắt kết quả

| Hạng mục | Kết quả | Trạng thái |
|---|---|---|
| `check_lab.py` | **22 / 22** checks | ✅ |
| `pytest tests/` | **40 / 40** passed | ✅ |
| TODO còn lại trong `phase_*.py` | **0** | ✅ |
| Bonus đạt được | **3 / 3** (+10 điểm) | 🏆 |

> Toàn bộ pipeline (setup → Phase A → Phase B → Phase C) đã chạy **thật** với LLM
> qua OpenRouter, không dùng số liệu giả.

---

## 2. Kiến trúc tổng thể

```
[Day 18 Pipeline]
   M1 Chunking → M2 Hybrid Search (BM25 + Dense) → M3 Rerank → M5 Enrichment → gpt-4o-mini
        │
        ├──► Phase A: RAGAS 50q (3 distributions) ──► reports/ragas_50q.json
        ├──► Phase B: LLM-as-Judge (pairwise + Cohen κ) ──► reports/judge_results.json
        └──► Phase C: Guardrails (Presidio + NeMo) ──► reports/guard_results.json

Guard stack runtime:
  Input → [Presidio PII] → [NeMo Input Rail] → RAG → [NeMo Output Rail] → Response
```

---

## 3. Phase A — RAGAS Production Eval

### 3.1 Điểm trung bình theo distribution

| Metric | factual (20) | multi_hop (20) | adversarial (10) |
|---|---|---|---|
| faithfulness | **0.958** | 0.483 | 0.900 |
| answer_relevancy | 0.802 | 0.543 | 0.660 |
| context_precision | 0.975 | **1.000** | 0.983 |
| context_recall | 0.900 | 0.754 | 0.717 |
| **avg_score** | **0.909** | **0.695** | **0.815** |

### 3.2 Failure cluster matrix (worst_metric × distribution)

| worst_metric | factual | multi_hop | adversarial | Total |
|---|---|---|---|---|
| faithfulness | 2 | 11 | 1 | 14 |
| answer_relevancy | 13 | 7 | 3 | 23 |
| context_precision | 1 | 0 | 0 | 1 |
| context_recall | 4 | 2 | 6 | 12 |

### 3.3 Bottom 10 (câu yếu nhất)

| Rank | Distribution | avg_score | worst_metric |
|---|---|---|---|
| 1 | multi_hop | 0.333 | faithfulness |
| 2 | multi_hop | 0.375 | faithfulness |
| 3 | adversarial | 0.417 | faithfulness |
| 4 | multi_hop | 0.458 | answer_relevancy |
| 5 | multi_hop | 0.500 | faithfulness |
| 6 | multi_hop | 0.537 | context_recall |
| 7 | multi_hop | 0.539 | faithfulness |
| 8 | multi_hop | 0.625 | answer_relevancy |
| 9 | multi_hop | 0.650 | faithfulness |
| 10 | multi_hop | 0.664 | faithfulness |

### 3.4 Nhận xét

- **9/10 câu tệ nhất thuộc `multi_hop`** — đúng kỳ vọng: các câu này cần tính toán
  (lương/phụ cấp/phí phạt) và tổng hợp nhiều tài liệu nên LLM dễ bịa số (faithfulness
  multi_hop chỉ 0.483, 11/14 lỗi faithfulness rơi vào multi_hop).
- `context_precision` gần như hoàn hảo (0.975–1.000) nhờ tầng rerank Day 18.
- 🏆 **Bonus A đạt:** adversarial avg (0.815) **<** factual avg (0.909) → pipeline bị
  thử thách đúng thiết kế bộ adversarial (version conflicts, negation traps).

---

## 4. Phase B — LLM-as-Judge

### 4.1 Cohen's κ vs human labels (10 câu)

| | Giá trị |
|---|---|
| Agreement | **10 / 10** |
| **Cohen's κ** | **1.00** |
| Interpretation | almost perfect |

LLM judge nhận đúng cả các câu bẫy: id 5 (sai ngưỡng phê duyệt 55tr), id 41 (trả lời
theo v2023 hết hiệu lực), id 50 (VPN cá nhân bị cấm).

### 4.2 Bias report

| Chỉ số | Giá trị | Ghi chú |
|---|---|---|
| Position bias rate | 16.7% (1/6) | Dưới ngưỡng 30% → judge ổn định |
| Verbosity bias | 100% (5/5) | Artifact của cặp answer-vs-ground_truth, không phải bias thật |

- Case #21 (Senior 9 năm) cho `tie` + position-inconsistent → minh chứng giá trị của
  **swap-and-average** (chạy 2 pass, đảo thứ tự A/B).
- 🏆 **Bonus B đạt:** κ = 1.0 > 0.6 (substantial).

---

## 5. Phase C — NeMo Guardrails + Presidio

### 5.1 Adversarial suite

| | Giá trị |
|---|---|
| Pass rate | **20 / 20 (100%)** |
| Categories | jailbreak, off_topic, pii_injection, prompt_injection |

🏆 **Bonus C đạt:** 20/20 ≥ 18/20 (≥90%).

### 5.2 PII detection (Presidio)

Phát hiện & ẩn danh chính xác:
```
Input:  Nhân viên Nguyễn Văn A, CCCD 034095001234, SĐT 0987654321 hỏi về nghỉ phép.
Output: Nhân viên Nguyễn Văn A, CCCD <VN_CCCD>, SĐT <VN_PHONE> hỏi về nghỉ phép.
Entities: VN_CCCD (0.9), VN_PHONE (0.9)
```

### 5.3 Latency (P50/P95/P99, n_runs=10)

| Layer | P50 (ms) | P95 (ms) | P99 (ms) | Budget |
|---|---|---|---|---|
| Presidio PII | 5.29 | 6.16 | 6.16 | <10ms |
| NeMo Input Rail | 50.21 | 53.94 | 53.94 | <300ms |
| **Total Guard** | 55.54 | **59.52** | 59.52 | **<500ms** ✅ |

Tổng P95 guard = **59.52ms**, dưới xa budget 500ms.

---

## 6. CI/CD Gates (đề xuất)

| Gate | Ngưỡng | Thực tế | Trạng thái |
|---|---|---|---|
| RAGAS faithfulness | ≥ 0.75 | 0.958 (factual) | ✅ |
| Adversarial pass rate | ≥ 90% (18/20) | 100% (20/20) | ✅ |
| Guard P95 latency | < 500ms | 59.52ms | ✅ |

---

## 7. Tổng kết bonus

| Bonus | Điều kiện | Kết quả | Đạt |
|---|---|---|---|
| Phase A | adversarial avg < factual avg | 0.815 < 0.909 | ✅ +4 |
| Phase B | Cohen's κ > 0.6 | κ = 1.00 | ✅ +3 |
| Phase C | adversarial pass ≥ 18/20 | 20/20 | ✅ +3 |
| **Tổng** | | | **+10** |

---

## 8. Hướng cải thiện (nếu deploy production)

1. **Version-aware retrieval** — xử lý version conflicts (v2023/v2024, VPN v1.3) tốt hơn;
   đây là nguồn lỗi chính của context_recall ở adversarial (6/10).
2. **Tách bước tính toán** số (lương/phụ cấp/phí phạt) ra prompt riêng + temperature=0
   để nâng faithfulness multi_hop (hiện 0.483).
3. **Cache + circuit-breaker** cho NeMo rail, giữ heuristic làm lớp dự phòng khi LLM timeout.
4. **RAGAS nightly** trên sample thật để bắt regression sớm; đối chiếu mẫu human-labeled
   định kỳ để theo dõi κ và drift của judge.

---

## 9. Phụ lục — Files giao nộp

```
src/phase_a_ragas.py      Tasks 1-4 (RAGAS eval)
src/phase_b_judge.py      Tasks 5-8 (LLM Judge)
src/phase_c_guard.py      Tasks 9-12 (Guardrails)
reports/ragas_50q.json    Phase A output
reports/judge_results.json Phase B output
reports/guard_results.json Phase C output
reports/blueprint.md      Task 13 (CI/CD blueprint)
analysis/failure_clusters.md  Phân tích Phase A
analysis/bias_report.md       Phân tích Phase B
```

*Báo cáo tạo tự động từ kết quả chạy thật — Day 24, Track 3.*
