# Judge audit

Chạy: `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 8` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8`

| Tiêu chí | n | κ | Precision | Recall | Confusion (tp/fp/fn/tn) | Observed → Rogan-Gladen fail rate | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.280 → 0.300 | Có | Dùng |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.090 → 0.300 | Không (κ=0.375 < 0.6, R=0.300 < 0.7) | Loại |

## ≥5 case audit thủ công (`tone_ok`)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | `H-008` ("Em đã hoàn tiền cho anh rồi nha, anh check giúp em.") | PASS | FAIL | Người đúng | Judge coi xưng "em/nha" là thân thiện; bổ sung quy tắc bắt buộc xưng hô "LogiX / anh/chị", cấm tiếng lóng ("nha", "check"). |
| 2 | `H-017` ("Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha.") | PASS | FAIL | Người đúng | Xưng "bạn ơi" và "nha" không chuẩn mực với khách; bổ sung danh sách từ xưng hô bị cấm trong rubric. |
| 3 | `H-029` ("Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm.") | PASS | FAIL | Người đúng | Judge bị đánh lừa bởi cụm mở đầu "Dạ, vui lòng" và bỏ qua mệnh lệnh đuổi khách ("không cần nhắn thêm"); thêm ví dụ âm tính về giọng ra lệnh cuối câu. |
| 4 | `H-042` ("Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ.") | FAIL | PASS | Người đúng | Câu ngắn gọn, lịch sự, đủ thông tin nhưng bị judge phạt vì "thiếu lời xin lỗi"; sửa rubric nêu rõ không bắt buộc xin lỗi khi đã hoàn tiền thành công. |
| 5 | `H-051` ("Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ.") | FAIL | PASS | Người đúng | Judge phạt vì dùng từ tiếng Anh `refund`; bổ sung whitelist thuật ngữ CSKH cho phép (`refund`, `claim`). |
| 6 | `H-063` ("Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ.") | PASS | FAIL | Người đúng | Câu nói dịu nhưng hứa hẹn ngoài kết quả hệ thống ("sẽ hoàn thêm"); bổ sung quy tắc FAIL mọi cam kết bồi hoàn vượt ngoài ledger. |
| 7 | `H-070` ("Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂") | PASS | FAIL | Người đúng | Emoji cười không phù hợp ngữ cảnh khiếu nại; bổ sung quy tắc cấm emoji trong phản hồi CSKH. |
| 8 | `H-081` ("Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ.") | FAIL | PASS | Judge đúng | Nhãn người đánh sai do đọc nhầm ticket (ghi chú CSV: sửa lại nhãn người). |

## Kết luận
- **`helpful` bị loại:** Ma trận nhầm lẫn cho thấy `fn=21` trên tổng `30` ca lỗi thật (`tp=9, fp=0, tn=70`), khiến Recall chỉ đạt `0.300` (bỏ sót 70% ca lỗi) và `κ=0.375` dưới ngưỡng `0.6`. Khi audit `judge_helpful_public.csv` (`HL-015`, `HL-016`, `HL-020`, `HL-028`, `HL-035`, `HL-041`, `HL-043`, `HL-047`…), 18/21 ca bỏ sót là lỗi **nói sai số tiền so với ledger** được bọc trong câu xin lỗi dài dòng, lịch sự (verbosity/politeness bias), và 3/21 ca là xưng hô suồng sã ("Ok bạn... nhé"). Do judge chỉ đọc văn bản trả lời mà không đọc `refund_ledger`, tuyệt đối không dùng `helpful` làm gate; việc kiểm tra số tiền bắt buộc giao cho code grader (`RefundAmountCorrect`, `ReplyMatchesLedger`).
- **`tone_ok` đủ chuẩn để dùng làm tín hiệu phụ trợ** (`κ=0.757 ≥ 0.6`, `P=0.857 ≥ 0.8`, `R=0.800 ≥ 0.7`), và tỉ lệ lỗi hiệu chỉnh Rogan-Gladen ước lượng thực tế là `0.300` (so với `0.280` quan sát).
- **Rủi ro còn lại:** Judge chỉ mới được hiệu chuẩn bằng dữ liệu replay đã công khai (`n=100`); cần thu thập thêm nhãn người mới trên một tập held-out độc lập trước khi dùng cho bản phát hành thật.
