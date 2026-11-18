# Bonus (+5đ): Port 3 grader sang Inspect AI và đối chiếu kết quả

3 grader được port sang `@scorer` của **Inspect AI** (`inspect-ai 0.3.291`, chạy offline qua `model="mockllm/model"`) trong [inspect_graders.py](../src/bonus/inspect_graders.py), dùng chung hàm đánh giá thuần với [graders.py](../src/lab9/graders.py) để đảm bảo không lệch logic:
1. `approval_bypass` (`ApprovalBypass`)
2. `refund_amount_correct` (`RefundAmountCorrect`)
3. `reply_matches_ledger` (`ReplyMatchesLedger` — FM-08)

## Cách chạy (môi trường bonus tách riêng, không làm nặng CI)
```bash
cd src
uv venv .venv-bonus --python 3.13
uv pip install --python .venv-bonus/bin/python -r requirements.txt -r requirements-lab9.txt -r requirements-bonus.txt
.venv-bonus/bin/python -m bonus.inspect_graders
.venv-bonus/bin/python -m pytest -q -o addopts= tests/test_bonus_inspect.py
```

## Kết quả đối chiếu (`eval_set_v1.jsonl`, 70 case/shape × 5 shape = 350 cases)
| Shape | Số ca lệch (mismatch) | `approval_bypass` (PE / Inspect) | `refund_amount_correct` (PE / Inspect) | `reply_matches_ledger` (PE / Inspect) |
|---|---|---|---|---|
| `swarm` | `0 / 70` | `0 / 0` | `0.9857 / 0.9857` | `1.0000 / 1.0000` |
| `fixed` | `0 / 70` | `0 / 0` | `1.0000 / 1.0000` | `1.0000 / 1.0000` |
| `seeded_regression` | `0 / 70` | `0 / 0` | `0.8571 / 0.8571` | `0.7857 / 0.7857` |
| `misreport_bonus` | `0 / 70` | `0 / 0` | `1.0000 / 1.0000` | `0.8571 / 0.8571` |
| `sibling_refund_bonus` | `0 / 70` | `20 / 20` | `0.7143 / 0.7143` | `1.0000 / 1.0000` |

**Kết luận:** Inspect AI `@scorer` tái lập chính xác 100% từng ca và toàn bộ điểm tổng hợp so với `pydantic-evals`, không cần API key.
