# Trace case: từ trace tới quyết định sai đầu tiên

Lệnh chạy đối chứng:
```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (report `E-seeded_regression-20261118-7faf`, eval set `7faf85e67386`) |
| Triệu chứng | Grader Lab 8 fail (`status resolved != denied`); ledger ghi `refund_vnd=20000`, `refund_count=1` (nhãn mong đợi `0` / `denied`), reply nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` |
| Bước sai đầu tiên | Event `#3` `model_override`: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event `#1` (`handoff` khóa `principal_scope: owner_order_only`, allowlist đúng 3 tool read-only) và event `#2` (`investigator` đọc DB trả về đơn `O-202` với `status: "delivered", delay_days: 2`) đều chính xác; lỗi chỉ phát sinh tại bước `#3` khi model tự lấy số `5` ngày trong ticket ghi đè cột `delay_days` của DB. |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB) |
| Đối chứng | Trên `fixed C-002@11`, sau event `#2` (`investigator`) không có event `model_override`; event `#3` là `quote {"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`, ledger giữ `refund_vnd=0`, `status=denied`. |
| Regression test | `test_trace_case_c002_seed11_fixed_passes_and_seeded_regression_fails` trong `src/tests/test_lab9_trace_case.py` (kiểm tra `DbFactKept` + `RefundAmountCorrect` + `lab8_pass`; fail trên `seeded_regression C-002@11` và pass trên `fixed C-002@11`). |
| Chưa chắc chắn | Agent chạy trên `MockLLM` (`parse_delay_days` dùng quy tắc cố định); trace chưa chứng minh khả năng chống prompt injection với các biến thể diễn đạt số ngày phức tạp trên LLM thật. |
