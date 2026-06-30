from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation."""
    zeros = {"faithfulness": 0.0, "answer_relevancy": 0.0,
             "context_precision": 0.0, "context_recall": 0.0, "per_question": []}
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from datasets import Dataset

        dataset = Dataset.from_dict({
            "question": questions, "answer": answers,
            "contexts": contexts, "ground_truth": ground_truths,
        })

        # Hỗ trợ OpenRouter: nếu OPENAI_BASE_URL trỏ tới provider không có embeddings,
        # cấu hình RAGAS dùng LLM qua base_url + embeddings LOCAL (sentence-transformers).
        eval_kwargs = {}
        base_url = os.getenv("OPENAI_BASE_URL", "") or os.getenv("OPENAI_API_BASE", "")
        if base_url:
            try:
                from langchain_openai import ChatOpenAI
                from langchain_community.embeddings import HuggingFaceEmbeddings
                model = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
                eval_kwargs["llm"] = ChatOpenAI(
                    model=model,
                    base_url=base_url,
                    api_key=os.getenv("OPENAI_API_KEY", ""),
                    temperature=0,
                )
                # Embeddings local — tránh gọi OpenAI embeddings (OpenRouter không có).
                eval_kwargs["embeddings"] = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
                print("  ℹ️  RAGAS dùng OpenRouter LLM + embeddings local.")
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️  Không cấu hình được RAGAS cho OpenRouter: {e}")

        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy,
                                            context_precision, context_recall],
                          **eval_kwargs)
        df = result.to_pandas()

        def _f(row, key):
            v = row.get(key, 0.0)
            try:
                return float(v) if v == v else 0.0  # NaN guard
            except (TypeError, ValueError):
                return 0.0

        per_question = [EvalResult(
            question=row["question"], answer=row["answer"],
            contexts=list(row["contexts"]), ground_truth=row["ground_truth"],
            faithfulness=_f(row, "faithfulness"),
            answer_relevancy=_f(row, "answer_relevancy"),
            context_precision=_f(row, "context_precision"),
            context_recall=_f(row, "context_recall"),
        ) for _, row in df.iterrows()]

        n = max(len(per_question), 1)
        return {
            "faithfulness": sum(r.faithfulness for r in per_question) / n,
            "answer_relevancy": sum(r.answer_relevancy for r in per_question) / n,
            "context_precision": sum(r.context_precision for r in per_question) / n,
            "context_recall": sum(r.context_recall for r in per_question) / n,
            "per_question": per_question,
        }
    except Exception as e:
        print(f"  ⚠️  RAGAS evaluation failed: {e}")
        return zeros


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating", "Tighten prompt, lower temperature"),
        "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
        "context_precision": ("Too many irrelevant chunks", "Add reranking or metadata filter"),
        "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
    }

    scored = []
    for r in eval_results:
        metrics = {
            "faithfulness": r.faithfulness,
            "answer_relevancy": r.answer_relevancy,
            "context_precision": r.context_precision,
            "context_recall": r.context_recall,
        }
        avg = sum(metrics.values()) / 4
        worst_metric = min(metrics, key=metrics.get)
        diagnosis, fix = diagnostic_tree[worst_metric]
        scored.append({
            "question": r.question,
            "worst_metric": worst_metric,
            "score": round(metrics[worst_metric], 4),
            "avg_score": round(avg, 4),
            "diagnosis": diagnosis,
            "suggested_fix": fix,
        })

    scored.sort(key=lambda x: x["avg_score"])
    return scored[:bottom_n]


def save_report(results: dict, failures: list[dict], path: str = "ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
