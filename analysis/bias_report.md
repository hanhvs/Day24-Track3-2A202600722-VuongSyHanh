# LLM Judge Bias Report — Phase B

**Sinh viên:** Vương Sỹ Hành (MSSV 2A202600722)
**Ngày:** Day 24 — Track 3
**Judge model:** openai/gpt-4o-mini (qua OpenRouter)

---

## 1. Pairwise Judge Results

*(swap_and_average() trên model_answer (A) vs ground_truth (B) — 6 cặp)*

| # | Question (tóm tắt) | Final Winner | Position Consistent? |
|---|---|---|---|
| demo | Nghỉ phép năm? (15 vs 12 ngày) | A | Yes |
| 1 | Nghỉ khi kết hôn | B | Yes |
| 5 | Mua thiết bị 55 triệu cần ai duyệt | B | Yes |
| 12 | Thưởng Tết tối thiểu | B | Yes |
| 21 | Senior 9 năm: phép + lương | tie | No |
| 23 | Hoàn trả đào tạo 25 triệu | B | Yes |

> Pairwise so model_answer với ground_truth: ground_truth (đáp án chuẩn) thường thắng (B),
> hợp lý. Câu 21 cho `tie` + position-inconsistent → ví dụ điển hình LLM judge phân vân khi
> 2 câu trả lời đều hợp lý → swap-and-average chuyển thành `tie` thay vì kết luận sai.

---

## 2. Swap-and-Average Results

| # | Final | Position Consistent? |
|---|---|---|
| demo (phép năm 15 vs 12) | A | Yes |
| 1, 5, 12, 23 | B | Yes |
| 21 (Senior 9 năm) | tie | **No** ← swap phát hiện inconsistency |

**Position bias rate:** 16.7% (1/6 case không nhất quán giữa 2 pass)
→ Dưới ngưỡng cảnh báo 30% → judge tương đối ổn định, nhưng vẫn có 1 case chứng minh
**giá trị của swap-and-average**: nếu chỉ chạy 1 pass, câu 21 có thể bị gán winner sai.

---

## 3. Cohen's κ Analysis

**Human labels:** `human_labels_10q.json` (10 câu, 6 label=1, 4 label=0)
**Judge labels:** direct grading qua gpt-4o-mini (`quality_label`): model_answer có đúng so với ground_truth không → 1/0

| Question ID | Human Label | Judge Label | Agree? |
|---|---|---|---|
| 1 | 1 | 1 | ✓ |
| 5 | 0 | 0 | ✓ |
| 12 | 1 | 1 | ✓ |
| 21 | 1 | 1 | ✓ |
| 23 | 1 | 1 | ✓ |
| 29 | 0 | 0 | ✓ |
| 33 | 1 | 1 | ✓ |
| 41 | 0 | 0 | ✓ |
| 46 | 1 | 1 | ✓ |
| 50 | 0 | 0 | ✓ |

**Cohen's κ:** **1.00**
**Interpretation:** almost perfect (10/10 agreement) → **đạt bonus κ > 0.6** ✓

> LLM judge đồng thuận tuyệt đối với human trên cả 10 câu, kể cả các câu bẫy: nhận đúng
> id 5 (sai ngưỡng phê duyệt 55tr), id 41 (trả lời theo v2023 hết hiệu lực), id 50 (VPN cá
> nhân bị cấm). Đây là minh chứng gpt-4o-mini đủ tin cậy làm judge cho domain HR policy này.

---

## 4. Verbosity Bias

Trong các case có winner rõ ràng (không phải tie) — 5 case decisive:
- A thắng + A dài hơn B: 1 / 5 cases
- B thắng + B dài hơn A: 4 / 5 cases
- **Verbosity bias rate:** 100% (5/5)

**Kết luận:** Con số 100% cần đọc cẩn thận trong ngữ cảnh này. Vì A = model_answer (câu RAG,
thường dài/đầy đủ) và B = ground_truth (đáp án chuẩn, súc tích), việc "winner dài hơn" ở đây
phần lớn là **artifact của cách dựng cặp** chứ không phải LLM thiên vị độ dài. Trong production,
chỉ số này cần đo trên các cặp answer-vs-answer thật (cùng phân phối độ dài) mới phản ánh đúng
verbosity bias; khi đó kỳ vọng tỉ lệ ~50%.

---

## 5. Nhận xét chung

> - **κ = 1.0 (almost perfect)** → LLM judge gpt-4o-mini rất đáng tin cho bài toán chấm
>   đúng/sai câu trả lời HR policy này; đạt bonus.
> - **Position bias 16.7%** (dưới 30%) → judge ổn định, nhưng case #21 cho thấy swap-and-average
>   là cần thiết để không kết luận sai khi LLM phân vân.
> - Verbosity bias 100% là artifact của thiết kế cặp (answer vs ground_truth), không phải
>   bias thật — bài học: luôn đo bias trên phân phối dữ liệu đại diện.
> - **Production:** dùng LLM judge với swap-and-average 2 pass, chỉ tin khi 2 pass đồng thuận;
>   định kỳ đối chiếu một mẫu human-labeled để theo dõi κ và bắt drift của model.
