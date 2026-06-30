# LLM Judge Bias Report — Phase B

**Sinh viên:** Vương Sỹ Hành (MSSV 2A202600722)
**Ngày:** Day 24 — Track 3
**Judge model:** gpt-4o-mini (chế độ heuristic fallback khi chưa có OPENAI_API_KEY)

---

## 1. Pairwise Judge Results

*(Chạy pairwise_judge() / swap_and_average() trên các cặp model_answer vs ground_truth)*

| # | Question (tóm tắt) | Winner | Reasoning tóm tắt |
|---|---|---|---|
| demo | Nghỉ phép năm? (15 vs 12 ngày) | A | Answer A đầy đủ hơn (heuristic theo độ dài) |
| 1 | Nghỉ khi kết hôn | tie/B | model_answer vs ground_truth |
| 5 | Mua thiết bị 55 triệu cần ai duyệt | B | ground_truth dài/đầy đủ hơn |
| 12 | Thưởng Tết tối thiểu | B | — |
| 21 | Senior 9 năm: phép + lương | B | — |
| 23 | Hoàn trả đào tạo 25 triệu | B | — |

> Lưu ý: đây là kết quả **heuristic** (so độ dài) vì chưa có API key. Khi bật LLM judge
> thật, winner/reasoning sẽ dựa trên 3 tiêu chí accuracy/completeness/conciseness.

---

## 2. Swap-and-Average Results

| # | Pass 1 Winner | Pass 2 Winner | Final | Position Consistent? |
|---|---|---|---|---|
| demo | A | A | A | Yes |

**Position bias rate:** 0% (heuristic deterministic → không có position bias).
Với LLM thật, swap-and-average là cơ chế chính để phát hiện và khử position bias.

---

## 3. Cohen's κ Analysis

**Human labels:** `human_labels_10q.json` (10 câu, 6 label=1, 4 label=0)
**Judge labels:** kết quả `quality_label()` so model_answer vs ground_truth trên 10 câu

| Question ID | Human Label | Judge Label | Agree? |
|---|---|---|---|
| 1 | 1 | 0 | ✗ |
| 5 | 0 | 0 | ✓ |
| 12 | 1 | 0 | ✗ |
| 21 | 1 | 0 | ✗ |
| 23 | 1 | 0 | ✗ |
| 29 | 0 | 0 | ✓ |
| 33 | 1 | 0 | ✗ |
| 41 | 0 | 0 | ✓ |
| 46 | 1 | 0 | ✗ |
| 50 | 0 | 0 | ✓ |

**Cohen's κ:** 0.00
**Interpretation:** slight / không đáng tin

> Giải thích: ở chế độ heuristic, `quality_label` so model_answer với ground_truth theo
> độ dài → ground_truth (thường ngắn gọn, chuẩn) hay "thắng" nên judge gán hầu hết = 0.
> Điều này khiến judge đồng thuận với human chỉ ở các câu human=0 (đúng 4/4), nhưng sai
> ở các câu human=1. **Để đạt κ>0.6 (bonus) cần LLM judge thật** — gpt-4o-mini đánh giá
> ngữ nghĩa sẽ nhận ra các câu model_answer đúng (human=1) và gán label=1.

---

## 4. Verbosity Bias

Trong các case có winner rõ ràng (không phải tie):
- A thắng + A dài hơn B: 1 / 6 cases
- B thắng + B dài hơn A: 5 / 6 cases
- **Verbosity bias rate:** 100% (artifact của heuristic dựa trên độ dài)

**Kết luận:** Con số 100% ở đây là **hệ quả trực tiếp** của heuristic (chọn answer dài
hơn), không phải bias thật của LLM. Đây minh hoạ chính xác *vì sao* verbosity bias nguy
hiểm: một judge chọn theo độ dài sẽ ưu tiên câu dài dù không chính xác hơn. Với LLM judge
thật, chỉ số này phải gần 50% mới coi là không thiên lệch.

---

## 5. Nhận xét chung

> - κ hiện tại = 0 (chế độ heuristic) → judge CHƯA đáng tin; cần `OPENAI_API_KEY` để
>   chạy gpt-4o-mini và kỳ vọng đạt κ>0.6 (substantial).
> - Position bias = 0% trong heuristic (deterministic). Cơ chế swap-and-average đã được
>   cài đặt đầy đủ và sẽ phát huy tác dụng khi judge là LLM (vốn có position bias).
> - Verbosity bias 100% là cảnh báo rõ ràng: không bao giờ để judge quyết định bằng độ dài.
> - Trong production: dùng LLM judge với swap-and-average (2 pass), chỉ tin kết quả khi
>   2 pass đồng thuận, kết hợp với một mẫu human-labeled định kỳ để theo dõi κ và bắt drift.
