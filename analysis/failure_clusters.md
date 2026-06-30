# Failure Cluster Analysis — Phase A

**Sinh viên:** Vương Sỹ Hành (MSSV 2A202600722)
**Ngày:** Day 24 — Track 3
**Eval:** RAGAS 4 metrics · 50 câu · LLM = openai/gpt-4o-mini (OpenRouter) · embeddings local

---

## 1. Aggregate RAGAS Scores theo Distribution

| Metric | factual | multi_hop | adversarial |
|---|---|---|---|
| faithfulness | 0.958 | 0.483 | 0.900 |
| answer_relevancy | 0.802 | 0.543 | 0.660 |
| context_precision | 0.975 | 1.000 | 0.983 |
| context_recall | 0.900 | 0.754 | 0.717 |
| **avg_score** | **0.909** | **0.695** | **0.815** |

---

## 2. Bottom 10 Questions

| Rank | Distribution | Question | avg_score | worst_metric |
|---|---|---|---|---|
| 1 | multi_hop | Nếu cần mua laptop 30 triệu cho nhân viên mới... | 0.333 | faithfulness |
| 2 | multi_hop | Manager thâm niên 12 năm: tổng phụ cấp hàng tháng... | 0.375 | faithfulness |
| 3 | adversarial | Manager dùng VPN cá nhân (NordVPN) khi WFH? | 0.417 | faithfulness |
| 4 | multi_hop | Senior 9 năm thâm niên nghỉ bao nhiêu ngày + lương... | 0.458 | answer_relevancy |
| 5 | multi_hop | Lương thử việc Junior mức cao nhất là bao nhiêu... | 0.500 | faithfulness |
| 6 | multi_hop | So sánh yêu cầu mật khẩu policy v1.0 vs v2.0... | 0.537 | context_recall |
| 7 | multi_hop | Tạm ứng 15 triệu, 20 ngày mới thanh toán... | 0.539 | faithfulness |
| 8 | multi_hop | So sánh bảo hiểm thử việc vs chính thức... | 0.625 | answer_relevancy |
| 9 | multi_hop | Tạm ứng 8 triệu, chưa thanh toán sau 30 ngày... | 0.650 | faithfulness |
| 10 | multi_hop | Công tác trong nước 2 ngày, khách sạn... | 0.664 | faithfulness |

→ **9/10 câu tệ nhất thuộc `multi_hop`** — đúng như kỳ vọng vì các câu này đòi hỏi tính toán + kết hợp nhiều tài liệu.

---

## 3. Failure Cluster Matrix

*(Mỗi ô = số câu có worst_metric = row, thuộc distribution = col)*

| worst_metric | factual | multi_hop | adversarial | Total |
|---|---|---|---|---|
| faithfulness | 2 | 11 | 1 | 14 |
| answer_relevancy | 13 | 7 | 3 | 23 |
| context_precision | 1 | 0 | 0 | 1 |
| context_recall | 4 | 2 | 6 | 12 |

---

## 4. Dominant Failure Analysis

**Dominant distribution (theo tổng số worst-metric hits):** factual (do answer_relevancy yếu nhất ở nhiều câu, dù avg_score factual cao)
**Dominant metric:** answer_relevancy (23 câu) — kế đến là faithfulness (14 câu)

**Lý do phân tích:**

> Có hai góc nhìn bổ sung nhau. Theo **avg_score**, `multi_hop` rõ ràng là yếu nhất
> (0.695 vs factual 0.909) — vì các câu này yêu cầu tính toán lương/phụ cấp/phí phạt và
> tổng hợp nhiều tài liệu, khiến LLM dễ bịa số (faithfulness multi_hop chỉ 0.483, và 11/14
> lỗi faithfulness rơi vào multi_hop). Theo **đếm worst_metric**, `answer_relevancy` là
> điểm yếu lan rộng nhất (23 câu) kể cả ở factual — phản ánh việc câu trả lời đôi khi đúng
> thông tin nhưng diễn đạt lệch trọng tâm câu hỏi. `context_precision` gần như hoàn hảo
> (0.975–1.000) nhờ tầng rerank của Day 18 hoạt động tốt.

---

## 5. Suggested Fixes

| Metric yếu | Root cause | Suggested fix |
|---|---|---|
| faithfulness | LLM bịa số khi phải tính toán (multi_hop) | Tách bước tính toán ra prompt riêng, hạ temperature=0, yêu cầu trích dẫn số từ context |
| context_recall | Thiếu chunk khi câu hỏi cần ghép nhiều policy (vd v1.0 vs v2.0) | Tăng HYBRID_TOP_K, thêm metadata version để pull đủ cả 2 phiên bản |
| context_precision | Hiếm khi lỗi (0.975+) | Giữ nguyên reranker hiện tại |
| answer_relevancy | Câu trả lời lệch trọng tâm câu hỏi | Cải thiện prompt template: yêu cầu trả lời trực tiếp câu hỏi trước, chi tiết sau |

---

## 6. Nhận xét về Adversarial Distribution

> **Bonus đạt:** avg_score adversarial (0.815) < factual (0.909) → pipeline ĐÃ bị "thử thách"
> đúng như thiết kế bộ adversarial. Đáng chú ý: faithfulness adversarial vẫn cao (0.900) —
> nghĩa là pipeline KHÔNG bịa đặt khi gặp bẫy, nhưng context_recall thấp (0.717, 6/10 lỗi
> context_recall ở adversarial) cho thấy điểm yếu thật là **không kéo đủ đúng phiên bản
> policy** khi có version conflict (v2023 vs v2024, VPN v1.3). Câu adversarial duy nhất lọt
> bottom-10 là câu VPN cá nhân NordVPN (rank 3, avg 0.417) — đúng loại bẫy "policy
> contradiction" mà bộ test nhắm tới. Hướng cải thiện: thêm version-aware retrieval để ưu
> tiên phiên bản policy mới nhất / đang hiệu lực.
