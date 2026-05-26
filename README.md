# Unit Test Agent

Hệ thống AI Agent tự động phân tích repository mã nguồn, lập kế hoạch kiểm thử, tự động sinh mã nguồn unit test (Java/Spring Boot, Python), thực thi kiểm thử và chạy phản hồi cải thiện tự sửa lỗi (Self-Correction Loop) cho đến khi đạt chỉ tiêu độ bao phủ mã nguồn (Target Coverage ≥ 90%).

---

## 1. Tính năng nổi bật

- **Phân tích AST Offline**: Tự động phát hiện ngôn ngữ (Java, Python) và phân tích cấu trúc mã nguồn (Lớp Service, dependency, phương thức, cyclomatic complexity) offline thông qua AST parser độc lập (`javalang` và `ast`).
- **Lên kế hoạch kiểm thử tự động**: Tự động hoạch định các ca test (Happy path, Edge case, Error path, Business logic) cho từng phương thức.
- **Tự động sửa lỗi cú pháp (Auto-fix loop)**: Khi LLM sinh mã test bị lỗi cú pháp, Agent tự động bắt lỗi và yêu cầu sửa lỗi tối đa 3 lần.
- **Thực thi và đo lường độ bao phủ**: Tích hợp chạy kiểm thử tự động thông qua `pytest` (Python) hoặc Maven/JaCoCo (Java) để trích xuất tỷ lệ bao phủ theo dòng/nhánh.
- **Vòng lặp phản hồi tự sửa lỗi (Self-Correction Loop)**: Tự động phát hiện các dòng mã chưa được phủ, sinh thêm ca test bổ sung nhắm tới các dòng bị thiếu cho đến khi đạt chỉ tiêu hoặc đạt giới hạn số lần thử (`max_retry = 3`).
- **Mô phỏng chạy Offline (Local Fallback)**: Khi không cấu hình OpenRouter API Key, Agent tự động chạy ở chế độ Local Fallback sinh mã mẫu và giả lập vòng lặp phản hồi giúp dễ dàng phát triển và kiểm định hệ thống.

---

## 2. Cấu trúc thư mục dự án

```text
unit-test-agent/
│
├── agent/
│   ├── orchestrator.py          # State machine của LangGraph
│   ├── state.py                 # Định nghĩa cấu trúc AgentState
│   ├── graph.py                 # Biên dịch đồ thị trạng thái Agent
│   │
│   ├── stages/
│   │   ├── stage1_analysis.py   # Code Analysis
│   │   ├── stage2_planning.py   # Test Planning
│   │   ├── stage3_generation.py # Test Generation & Auto-fix
│   │   ├── stage4_execution.py  # Test Execution & XML Parsing
│   │   └── stage5_correction.py # Self-Correction Feedback Loop
│   │
│   ├── parsers/
│   │   ├── java_parser.py       # Java AST parser (javalang)
│   │   └── python_parser.py     # Python AST parser (ast)
│   │
│   └── llm/
│       ├── client.py            # OpenRouter API client
│       └── prompts.py           # System / User prompts
│
├── schemas/                     # Các JSON Schema xác thực dữ liệu
│   ├── analysis_result.schema.json
│   ├── test_plan.schema.json
│   └── coverage_report.schema.json
│
├── tests/                       # Unit & Integration tests cho chính Agent
│
├── .env.example                 # Mẫu cấu hình biến môi trường
├── config.yaml                  # File cấu hình chung
├── main.py                      # CLI entrypoint của dự án
├── requirements.txt             # Danh sách dependencies
└── README.md                    # Tài liệu hướng dẫn sử dụng
```

---

## 3. Hướng dẫn cài đặt

### Yêu cầu hệ thống
- Python 3.10 trở lên
- JDK 17+ / Maven (nếu kiểm thử dự án Java)

### Các bước cài đặt
1. Tạo môi trường ảo và kích hoạt:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate   # Trên Windows
   source venv/bin/activate  # Trên macOS/Linux
   ```

2. Cài đặt các gói phụ thuộc:
   ```bash
   pip install -r requirements.txt
   ```

3. Cấu hình file môi trường `.env`:
   Sao chép tệp cấu hình mẫu và điền OpenRouter API Key:
   ```bash
   copy .env.example .env
   ```
   Nội dung file `.env`:
   ```env
   OPENROUTER_API_KEY=your-openrouter-key-here
   ```

---

## 4. Hướng dẫn sử dụng

Chạy chương trình thông qua giao diện dòng lệnh (CLI):
```bash
python main.py --repo <path_to_your_project>
```

**Ví dụ:**
```bash
python main.py --repo D:\my-spring-boot-project
```

Chương trình sẽ hiển thị chi tiết lịch sử thực thi từng giai đoạn, sinh tệp kiểm thử trong thư mục `generated_tests/` của repository đích và ghi lại tệp `test_plan.json` cũng như `coverage_report.json`.

---

## 5. Chạy kiểm thử cho Agent

Để thực thi 17 bài kiểm tra tự động xác minh toàn bộ logic của Agent:
```bash
pytest tests/
```
