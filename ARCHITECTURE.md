# ARCHITECTURE.md — Unit Test Agent (90CovUnitest)

> **Mục đích của tài liệu này:** Hướng dẫn toàn diện cho AI Agent để nắm bắt hoàn toàn cấu trúc, luồng hoạt động, dữ liệu, và các quy ước lập trình của dự án `90CovUnitest`. Đọc hết tài liệu này trước khi thực hiện bất kỳ thay đổi nào.

---

## 1. Tổng quan hệ thống

**90CovUnitest** là một AI Agent tự động sinh unit test cho codebase Java (Spring Boot) và Python, với mục tiêu đạt **≥ 90% code coverage**. Hệ thống sử dụng kiến trúc **LangGraph State Machine** để điều phối pipeline gồm 5 giai đoạn tuần tự, có vòng lặp tự sửa lỗi (self-correction loop).

### Hai chế độ vận hành

| Chế độ | Điều kiện | Mô tả |
|---|---|---|
| **LLM Mode** | `OPENROUTER_API_KEY` hợp lệ | Dùng AI (Kimi K2.6, DeepSeek V4) để phân tích và sinh test |
| **Local Fallback** | Không có API key | Sinh test từ AST offline, không gọi LLM |

### Hai giao diện người dùng

| Giao diện | Entrypoint | Mô tả |
|---|---|---|
| **CLI** | `main.py` | Chạy toàn bộ pipeline tự động, không tương tác |
| **Web Dashboard (HITL)** | `server.py` | FastAPI server, cho phép người dùng duyệt test cases trước khi chạy |

---

## 2. Cấu trúc thư mục chi tiết

```
90CovUnitest/
│
├── main.py                    # CLI entrypoint — chạy pipeline đầu-cuối
├── server.py                  # FastAPI Web server với HITL (Human-in-the-Loop)
├── config.yaml                # Cấu hình model LLM, timeout, coverage threshold
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container build
├── docker-compose.yml         # Docker Compose orchestration
├── verify_pipeline.py         # Script kiểm tra pipeline thủ công
│
├── agent/                     # Core logic của Agent
│   ├── __init__.py
│   ├── state.py               # Định nghĩa AgentState (TypedDict)
│   ├── graph.py               # Biên dịch LangGraph StateGraph
│   ├── progress.py            # Thread-safe progress tracking (ContextVar)
│   │
│   ├── stages/                # 5 giai đoạn xử lý
│   │   ├── __init__.py
│   │   ├── stage1_analysis.py   # Phân tích cấu trúc code (AST + LLM)
│   │   ├── stage2_planning.py   # Lập kế hoạch test cases
│   │   ├── stage3_generation.py # Sinh mã test + auto-fix loop
│   │   ├── stage4_execution.py  # Chạy pytest/Maven, đo coverage
│   │   └── stage5_correction.py # Self-correction feedback loop
│   │
│   ├── parsers/               # AST parser offline (không cần LLM)
│   │   ├── java_parser.py     # Dùng thư viện `javalang`
│   │   └── python_parser.py   # Dùng module `ast` của Python stdlib
│   │
│   └── llm/
│       ├── client.py          # OpenRouter API client (wrapper OpenAI SDK)
│       └── prompts.py         # Toàn bộ system/user prompt cho từng stage
│
├── schemas/                   # JSON Schema để validate dữ liệu giữa các stage
│   ├── analysis_result.schema.json
│   ├── test_plan.schema.json
│   └── coverage_report.schema.json
│
├── static/                    # Web UI files
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── tests/                     # Unit tests cho chính Agent (không phải target project)
│   ├── test_stage1.py
│   ├── test_stage2.py
│   ├── test_stage3.py
│   ├── test_stage4.py
│   ├── test_stage5.py
│   ├── test_graph.py
│   ├── test_parsers.py
│   ├── test_server.py
│   ├── test_main.py
│   ├── test_env.py
│   └── test_hitl_pipeline.py
│
└── demo_project/              # Dự án mẫu để test Agent
    ├── app/services/
    │   └── calculator_service.py   # Service Python mẫu (add, divide)
    ├── generated_tests/            # Output được sinh ra bởi Agent
    │   └── app/services/test_calculator_service.py
    ├── test_plan.json              # Kế hoạch test đã sinh
    └── coverage_report.json        # Báo cáo coverage đã sinh
```

---

## 3. Kiến trúc dữ liệu trung tâm — `AgentState`

Đây là object duy nhất được truyền xuyên suốt toàn bộ pipeline. Mọi stage đều nhận vào `AgentState` và trả về `AgentState`.

```python
# agent/state.py
class AgentState(TypedDict):
    repo_path: str                        # Đường dẫn tuyệt đối tới project cần test
    language: str                         # "java" | "python" | "typescript"
    framework: str                        # "spring-boot" | "fastapi" | "nestjs"
    service_files: List[str]              # Danh sách relative path các file service cần test
    analysis_result: Optional[Dict]       # Output của Stage 1 (theo analysis_result.schema.json)
    test_plan: Optional[Dict]             # Output của Stage 2 (theo test_plan.schema.json)
    generated_tests: List[Dict]           # Output của Stage 3: [{"service": ..., "file_path": ...}]
    coverage_report: Optional[Dict]       # Output của Stage 4 (theo coverage_report.schema.json)
    retry_count: int                      # Số lần đã retry self-correction loop
    history: List[str]                    # Log các bước đã hoàn thành dạng text
```

**Quy tắc quan trọng về state:**
- Không được tự ý thêm key mới vào `AgentState` — phải khai báo trong `state.py`
- Mỗi stage chỉ được `set` giá trị vào state, không được `delete` key
- `retry_count` chỉ được tăng bởi `Stage5Correction`

---

## 4. Luồng pipeline — LangGraph State Machine

```
[START]
    │
    ▼
Stage 1: Code Analysis          (stage1_analysis.py)
    │  Phát hiện ngôn ngữ, parse AST, gọi LLM enrichment
    │  Output: state["analysis_result"], state["language"], state["service_files"]
    ▼
Stage 2: Test Planning          (stage2_planning.py)
    │  Dựa vào analysis_result, sinh test cases (happy/edge/error)
    │  Output: state["test_plan"]
    ▼
Stage 3: Test Generation        (stage3_generation.py)
    │  Gọi LLM sinh code test, kiểm tra syntax, auto-fix tối đa 3 lần
    │  Output: state["generated_tests"], files trong {repo}/generated_tests/
    ▼
Stage 4: Test Execution         (stage4_execution.py)
    │  Chạy pytest/Maven, parse coverage.xml hoặc jacoco.xml
    │  Output: state["coverage_report"]
    ▼
Stage 5: Self-Correction        (stage5_correction.py)
    │  Kiểm tra coverage >= target (90%)
    │  Nếu chưa đủ VÀ retry_count < max_retry (3):
    │      tăng retry_count, cập nhật test_plan, → quay lại Stage 3
    │  Nếu đủ HOẶC hết retry:
    │      → END
    ▼
[END]
```

### Conditional Edge (vòng lặp)

```python
# agent/graph.py — hàm should_continue_loop
def should_continue_loop(state: AgentState) -> str:
    current_coverage = coverage_report.get("total_coverage", 0.0)
    target_coverage  = float(test_plan.get("target_coverage", 90.0))
    retry_count      = state.get("retry_count", 0)
    max_retry        = config.get("max_retry", 3)

    if current_coverage >= target_coverage or retry_count >= max_retry:
        return END
    return "stage3_generation"   # Quay lại Stage 3
```

---

## 5. Phân tích từng Stage

### Stage 1 — Code Analysis (`stage1_analysis.py`)

**Nhiệm vụ:** Phát hiện ngôn ngữ, tìm service files, parse AST, (tuỳ chọn) enrich bằng LLM.

**Bước thực thi:**
1. `detect_language_and_framework(repo_path)` — quét file `pom.xml`, `build.gradle`, `package.json`, `requirements.txt`
2. `discover_service_files(repo_path, language)` — tìm file có chứa "service" trong tên/đường dẫn; bỏ qua `venv`, `.git`, `tests`, `generated_tests`
3. Với mỗi file service:
   - Chạy local AST parser (`JavaParser` hoặc `PythonParser`) → `local_parse`
   - Nếu có API key: gọi LLM với `STAGE1_USER_PROMPT_TEMPLATE`, kết quả enrich `local_parse`
   - Nếu không có API key: dùng trực tiếp `local_parse`
4. Validate kết quả bằng `analysis_result.schema.json`
5. Lưu vào `state["analysis_result"]`

**Output schema** (`analysis_result`):
```json
{
  "repo": { "path": "...", "language": "python", "framework": "fastapi", "build_tool": "pip" },
  "services": [
    {
      "class_name": "CalculatorService",
      "package": "",
      "file_path": "app/services/calculator_service.py",
      "annotations": [],
      "methods": [
        {
          "name": "divide",
          "visibility": "public",
          "params": [{"name": "a", "type": "float"}, {"name": "b", "type": "float"}],
          "return_type": "float",
          "throws": ["ValueError"],
          "annotations": [],
          "complexity": 2,
          "priority": "MEDIUM"
        }
      ],
      "dependencies": []
    }
  ]
}
```

**Lưu ý quan trọng:**
- `priority` chỉ nhận giá trị: `"HIGH"` | `"MEDIUM"` | `"LOW"`
- `category` của dependency chỉ nhận: `"repository"` | `"http_client"` | `"message_queue"` | `"cache"` | `"service"` | `"utility"`
- Model LLM mặc định: `deepseek/deepseek-v4-flash` (config.yaml), fallback code dùng `kimi/kimi-k2.6`

---

### Stage 2 — Test Planning (`stage2_planning.py`)

**Nhiệm vụ:** Từ `analysis_result`, sinh kế hoạch test cases theo từng method.

**Bước thực thi:**
1. Kiểm tra API key → chọn LLM hoặc local fallback
2. **LLM mode:** Gọi DeepSeek với `STAGE2_USER_PROMPT_TEMPLATE`, nhận JSON `test_plan`
3. **Local fallback:** `generate_local_fallback_plan()` sinh tự động:
   - 1 `happy_path` per method (inputs hợp lệ)
   - 1 `edge_case` per method (nếu có params — truyền `null`)
   - 1 `error_path` per method (nếu có `throws` hoặc dependencies)
4. Sanitize: convert tất cả `input` values thành `str`, convert `return_value` thành `str`
5. Validate bằng `test_plan.schema.json`

**Output schema** (`test_plan`):
```json
{
  "plan_version": "1.0",
  "target_coverage": 90,
  "test_cases": [
    {
      "service": "CalculatorService",
      "method": "divide",
      "test_id": "CalculatorService_divide_001",
      "type": "happy_path",
      "description": "Chia hai số dương hợp lệ",
      "setup": {
        "mocks": [
          { "dependency": "userRepo", "method": "findById", "behavior": "return", "return_value": "mockUser" }
        ]
      },
      "input": { "a": "10.0", "b": "2.0" },
      "expected": {
        "return_type": "float",
        "assertions": ["result == 5.0"],
        "verify_mocks": [],
        "throws": null,
        "exception_message_contains": null
      }
    }
  ]
}
```

**Quy ước test_id:** `{ClassName}_{methodName}_{3 chữ số}` — ví dụ: `UserService_getUserById_001`

---

### Stage 3 — Test Generation (`stage3_generation.py`)

**Nhiệm vụ:** Sinh file test code từ `test_plan`, tự động sửa lỗi syntax.

**Bước thực thi:**
1. Group test cases theo `service` name
2. Với mỗi service:
   - Đọc source code gốc từ `repo_path`
   - **LLM mode:** `generate_llm_code_with_autofix()`:
     - Gọi `kimi/kimi-k2.6` với system prompt + source code + test cases JSON
     - Extract code block từ response (`extract_code_block()`)
     - `check_syntax()`: compile Python AST hoặc `javalang.parse.parse()`
     - Nếu lỗi: thêm error vào messages, gọi lại LLM (tối đa 3 lần)
     - Sau lần 2: tự động đổi sang model fallback `deepseek/deepseek-v4-pro`
   - **Local fallback:** `generate_local_fallback_code()` sinh JUnit 5 (Java) hoặc pytest (Python) template
3. Lưu file vào `{repo_path}/generated_tests/{mirrored_path}`
   - Python: `app/services/user_service.py` → `generated_tests/app/services/test_user_service.py`
   - Java: `src/main/java/com/example/UserService.java` → `generated_tests/com/example/UserServiceTest.java`

**Kết quả ghi vào state:**
```python
state["generated_tests"] = [
    {"service": "CalculatorService", "file_path": "generated_tests/app/services/test_calculator_service.py"}
]
```

**Lỗi:** Nếu generation thất bại, ghi vào `{repo_path}/failed_methods.log`

---

### Stage 4 — Test Execution (`stage4_execution.py`)

**Nhiệm vụ:** Thực thi các file test đã sinh, đo coverage.

**Python:**
```bash
pytest --cov=. --cov-report=xml generated_tests/
```
- Tìm `pytest` trong `venv/Scripts/pytest.exe` hoặc `.venv/Scripts/pytest.exe`
- Set `PYTHONPATH` bao gồm toàn bộ thư mục con có `.py` file
- Parse `coverage.xml` bằng `parse_python_coverage_xml()`:
  - Bỏ qua file test (có `test_` trong tên)
  - Lấy `line-rate`, danh sách `uncovered_lines`, `branch-rate`
  - Parse `passed`/`failed` từ stdout (`"N passed"`, `"N failed"`)

**Java:**
- Tìm `target/site/jacoco/jacoco.xml`
- Parse bằng `parse_jacoco_xml()`:
  - Đếm `covered`/`missed` từ `<counter type="LINE">`
  - Thu thập `uncovered_lines` từ `<line mi>0 ci>0` conditions

**Output schema** (`coverage_report`):
```json
{
  "total_coverage": 85.5,
  "summary": { "total_tests": 6, "passed": 6, "failed": 0, "skipped": 0 },
  "classes": {
    "calculator_service": {
      "line_coverage": 85.5,
      "branch_coverage": 80.0,
      "uncovered_lines": [12, 15]
    }
  },
  "failures": []
}
```

**Quan trọng:** Stage 4 **THROW RuntimeError** nếu test execution thất bại — không có silent failure.

---

### Stage 5 — Self-Correction (`stage5_correction.py`)

**Nhiệm vụ:** Kiểm tra coverage, quyết định dừng hoặc trigger retry.

**Logic:**
```
if current_coverage >= target_coverage:  → END (thành công)
if retry_count >= max_retry (3):          → END (đã hết retry)
else:
    retry_count += 1
    Gọi LLM với test_plan + coverage_report
    LLM sinh test_plan mới với test cases bổ sung nhắm vào uncovered_lines
    state["test_plan"] = updated_plan
    → Graph routing quay lại Stage 3
```

**Fallback:** Nếu không có API key, Stage 5 **THROW RuntimeError** — không có local fallback cho self-correction.

---

## 6. LLM Client (`agent/llm/client.py`)

### `OpenRouterClient`

```python
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)
```

**Retry logic:** 3 lần, exponential backoff (2s, 4s, 8s)

**Headers bắt buộc:**
```python
extra_headers = {
    "HTTP-Referer": "https://github.com/anhluong447/90CovUnitest",
    "X-Title": "Unit Test Agent"
}
```

**Phát hiện mock key:** Nếu `api_key` bắt đầu bằng `"your-openrouter-api-key"` → trả về `'{"mocked": true}'`

### `clean_json_response(content: str) -> str`

Hàm tiện ích xử lý LLM response bẩn:
1. Strip markdown code fence ` ```json ` hoặc ` ``` `
2. Tìm `{` đầu tiên và `}` cuối cùng để extract JSON thuần

---

## 7. Parsers (`agent/parsers/`)

### `PythonParser` (dùng `ast` stdlib)

- Kế thừa `ast.NodeVisitor`
- `visit_ClassDef()`: parse class, `__init__` args (→ dependencies), methods
- Phát hiện category dependency từ tên biến/type: `repo` → repository, `cache`/`redis` → cache, `client`/`http` → http_client, `kafka`/`mq` → message_queue
- Tính `complexity`: đếm `If`, `For`, `While`, `ExceptHandler`, `With` nodes + `BoolOp` values
- `visibility`: `__method` → private, `_method` → protected, còn lại → public

### `JavaParser` (dùng `javalang`)

- `parse_file(file_path, source_code)` → static method
- Parse `FieldDeclaration` → dependencies (phát hiện `@Autowired`, `@MockBean`, `@Spy`)
- Parse `MethodDeclaration` → methods (visibility từ `modifiers`, return type, params, throws)
- Tính complexity: đếm `IfStatement`, `ForStatement`, `WhileStatement`, `DoStatement`, `CatchClause`, `SwitchStatementCase`

---

## 8. Prompts (`agent/llm/prompts.py`)

Đây là file quan trọng nhất cho chất lượng output LLM. Tất cả prompts đều được viết bằng **tiếng Việt**.

| Prompt | Stage | Model | Định dạng output |
|---|---|---|---|
| `STAGE1_SYSTEM_PROMPT` + `STAGE1_USER_PROMPT_TEMPLATE` | Stage 1 | DeepSeek/Kimi | JSON Object (service metadata) |
| `STAGE2_SYSTEM_PROMPT` + `STAGE2_USER_PROMPT_TEMPLATE` | Stage 2 | DeepSeek | JSON Object (test_plan) |
| `STAGE3_SYSTEM_PROMPT_JAVA` | Stage 3 | Kimi | Code block ` ```java ` |
| `STAGE3_SYSTEM_PROMPT_PYTHON` | Stage 3 | Kimi | Code block ` ```python ` |
| `STAGE3_USER_PROMPT_TEMPLATE` | Stage 3 | - | - |
| `STAGE3_AUTO_FIX_PROMPT` | Stage 3 (retry) | Kimi/DeepSeek | Code block ` ```... ` |
| `STAGE5_SYSTEM_PROMPT` + `STAGE5_USER_PROMPT_TEMPLATE` | Stage 5 | Kimi | JSON Object (updated test_plan) |

**Quy tắc tất cả system prompts:**
- Luôn yêu cầu "CHỈ trả về JSON thô / code block, KHÔNG giải thích"
- Stage 1: 6 danh mục dependency cố định
- Stage 2: 4 loại test case cố định (`happy_path`, `edge_case`, `error_path`, `business`)

---

## 9. Web Server — HITL Mode (`server.py`)

### Kiến trúc HITL (Human-in-the-Loop)

```
POST /api/run  →  Phase 1 (Stage 1 + Stage 2) chạy background
                      └─→ status = "awaiting_user_approval"

[User review test cases trên Web UI]

POST /api/resume/{run_id}  →  Phase 2 (Stage 3 + 4 + 5) chạy background
                                └─→ status = "completed" | "failed"
```

### In-memory state (`runs_db`)

```python
# agent/progress.py
runs_db: Dict[str, Dict[str, Any]] = {}   # Global dictionary, key = run_id (UUID)

runs_db[run_id] = {
    "run_id": str,
    "repo_path": str,
    "status": "running" | "awaiting_user_approval" | "completed" | "failed",
    "logs": List[str],           # Log lines từ logging handler
    "test_plan": Dict,
    "coverage_report": Dict,
    "history": List[str],
    "generated_files": List[{"path": str, "content": str}],
    "agent_state": Dict,         # Snapshot AgentState sau Phase 1
    "progress": {
        "stage": int,            # Stage hiện tại (1-5)
        "percentage": int,       # 0-100
        "message": str,          # Message hiển thị trên UI
        "status": str,
        "stage_data": Dict       # Data bổ sung (danh sách file đang xử lý...)
    },
    "error": str | None
}
```

### Progress tracking (`agent/progress.py`)

```python
current_run_id = contextvars.ContextVar("current_run_id", default=None)

def update_progress(stage, percentage, message, stage_data=None):
    run_id = current_run_id.get()   # Lấy run_id từ context của thread hiện tại
    # Cập nhật runs_db[run_id]["progress"]
```

**Quan trọng:** Mỗi background thread (FastAPI `BackgroundTasks`) set `current_run_id` bằng `contextvars.ContextVar.set()` trước khi chạy, và `reset()` trong `finally`.

### API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/run` | Bắt đầu Phase 1. Body: `{"repo_path": "..."}` |
| `POST` | `/api/resume/{run_id}` | Bắt đầu Phase 2. Body: `{"selected_test_ids": [...]}` |
| `GET` | `/api/status/{run_id}` | Lấy toàn bộ trạng thái của run |
| `GET` | `/api/runs` | Liệt kê tất cả runs |
| `GET` | `/api/list-dirs` | Duyệt thư mục server (base `/app`) |
| `GET` | `/` | Serve `static/index.html` |

### `RunLogHandler` (logging)

Custom logging handler tự động ghi mọi log vào `runs_db[run_id]["logs"]` dựa trên `current_run_id` contextvar.

---

## 10. Configuration (`config.yaml`)

```yaml
models:
  stage1: "deepseek/deepseek-v4-flash"   # Model phân tích code
  stage2: "deepseek/deepseek-v4-flash"   # Model lập kế hoạch
  stage3: "deepseek/deepseek-v4-flash"   # Model sinh test code (primary)
  stage3_fallback: "deepseek/deepseek-v4-flash"  # Dùng khi primary fail 2 lần
  stage5: "deepseek/deepseek-v4-flash"   # Model self-correction

coverage:
  line_threshold: 90    # Target line coverage (%)
  branch_threshold: 80  # Target branch coverage (%)
  max_retries: 5        # Max retry cho coverage loop

execution:
  timeout_seconds: 600         # Timeout chạy test
  docker_memory_limit: "4g"
  docker_cpu_limit: 2

mutation:
  enabled: false    # Mutation testing (chưa implement)
```

**Truy cập trong code:** `config.get("models", {}).get("stage1", "kimi/kimi-k2.6")` — giá trị mặc định trong code có thể khác config.yaml.

---

## 11. JSON Schemas (`schemas/`)

Ba schema dùng `jsonschema.validate()` để đảm bảo contract giữa stages.

### `analysis_result.schema.json` — Validate output Stage 1

**Required fields:** `repo` (path, language, framework) và `services[]` (class_name, file_path, methods[], dependencies[])

**Enum constraints:**
- `method.priority`: `["HIGH", "MEDIUM", "LOW"]`
- `dependency.category`: `["repository", "http_client", "message_queue", "cache", "service", "utility"]`

### `test_plan.schema.json` — Validate output Stage 2

**Required fields:** `plan_version`, `target_coverage`, `test_cases[]`

**Enum constraints:**
- `test_case.type`: `["happy_path", "edge_case", "error_path", "business"]`
- `mock.behavior`: `["return", "throw", "do_nothing"]`
- `input` và `mock.return_value`: **phải là `string`** — Stage 2 tự động convert

### `coverage_report.schema.json` — Validate output Stage 4

**Required fields:** `total_coverage` (number), `summary` (total_tests, passed, failed, skipped), `classes` (dict), `failures[]`

---

## 12. Demo Project (`demo_project/`)

Dự án mẫu để chạy thử Agent.

```python
# demo_project/app/services/calculator_service.py
class CalculatorService:
    def add(self, a: float, b: float) -> float:
        return a + b

    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
```

**Generated test** (sau khi Agent chạy):
```python
# demo_project/generated_tests/app/services/test_calculator_service.py
class TestCalculatorService:
    def test_add_positive_numbers(self, calculator_service):     # happy path
    def test_add_negative_and_positive(self, calculator_service): # edge case
    def test_add_zeros(self, calculator_service):                 # edge case
    def test_divide_positive_numbers(self, calculator_service):  # happy path
    def test_divide_zero_dividend(self, calculator_service):     # edge case
    def test_divide_by_zero_raises_value_error(self, calculator_service):  # error path
```

**Chạy thử:**
```bash
python main.py --repo ./demo_project
```

---

## 13. Môi trường và cài đặt

### Environment Variables

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `OPENROUTER_API_KEY` | Không (có fallback) | Key để gọi OpenRouter LLM API |

### Dependencies chính

| Package | Vai trò |
|---|---|
| `langgraph` | State machine pipeline |
| `langchain-core` | Core abstractions |
| `openai` | SDK gọi OpenRouter (dùng `base_url` override) |
| `javalang` | Java AST parser offline |
| `jsonschema` | Validate JSON giữa các stage |
| `fastapi` + `uvicorn` | Web server HITL |
| `pytest` + `pytest-cov` | Chạy test Python trong target project |
| `pyyaml` | Đọc `config.yaml` |
| `python-dotenv` | Load `.env` |

### Cài đặt

```bash
python -m venv venv
source venv/bin/activate  # hoặc venv\Scripts\activate trên Windows
pip install -r requirements.txt

# Tạo .env
echo "OPENROUTER_API_KEY=your-key-here" > .env

# Chạy CLI
python main.py --repo ./demo_project

# Hoặc Web Server
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
docker-compose up --build
# Web UI tại http://localhost:8000
```

---

## 14. Quy ước code và các pattern quan trọng

### Pattern 1: Stage Class Structure

Mỗi stage là một class với pattern chuẩn:
```python
class StageN:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()     # Luôn khởi tạo client
        self.model = config.get("models", {}).get("stageN", "default-model")

    def run(self, state: AgentState) -> AgentState:
        # 1. Validate input từ state
        # 2. update_progress(N, percentage, message)
        # 3. Xử lý logic (LLM hoặc local fallback)
        # 4. Validate output bằng jsonschema
        # 5. state["output_key"] = result
        # 6. state["history"].append("Stage N completed: ...")
        # 7. update_progress(N, 100, "Hoàn thành Stage N")
        return state
```

### Pattern 2: LLM Fallback

```python
if not self.llm_client.api_key or self.llm_client.api_key.startswith("your-openrouter-api-key"):
    result = self.local_fallback_method(...)
else:
    try:
        result = self.call_llm(...)
    except Exception as e:
        logger.error(f"LLM failed: {e}. Falling back to local.")
        result = self.local_fallback_method(...)
```

### Pattern 3: JSON Schema Validation

```python
schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                           "schemas", "xxx.schema.json")
with open(schema_path, "r", encoding="utf-8") as f:
    schema = json.load(f)
try:
    validate(instance=result, schema=schema)
except Exception as e:
    logger.error(f"Validation failed: {e}")  # Log nhưng KHÔNG crash
```

### Pattern 4: Progress Update

```python
update_progress(stage_number, percentage_int, "Thông báo tiếng Việt", {
    "optional_stage_data_key": value
})
```

---

## 15. Các điểm cần chú ý khi sửa code

1. **Thêm language mới:** Cần sửa `detect_language_and_framework()`, `discover_service_files()`, `generate_local_fallback_code()`, thêm parser mới trong `parsers/`, thêm system prompt trong `prompts.py`.

2. **Thay đổi schema:** Sửa file JSON schema tương ứng trong `schemas/`, kiểm tra tất cả code sanitize dữ liệu trước khi validate (đặc biệt Stage 2 convert values sang string).

3. **Thêm LLM model:** Sửa `config.yaml`, mọi nơi khác lấy model từ config qua `config.get("models", {}).get("stageX", "default")`.

4. **`runs_db` là in-memory:** Restart server sẽ mất toàn bộ history. Nếu cần persistence, phải tích hợp Redis/database.

5. **Stage 4 Java:** Hiện tại chỉ đọc `jacoco.xml` có sẵn, **không tự chạy Maven**. Cần cải thiện nếu muốn tích hợp CI/CD đầy đủ.

6. **`failed_methods.log`:** Ghi append, không clear giữa các run. Cần xóa thủ công hoặc thêm logic clear khi bắt đầu run mới.

7. **Thread safety:** `runs_db` là dict thông thường (không lock). FastAPI Background Tasks chạy trong thread pool — có thể race condition nếu nhiều runs cùng lúc sửa cùng `run_id`.

---

## 16. Ví dụ chạy và kết quả mong đợi

```bash
$ python main.py --repo ./demo_project

# Log output:
# [INFO] Detected: language=python, framework=fastapi, build_tool=pip
# [INFO] Discovered 1 service files to analyze.
# [INFO] Starting Stage 2: Test Planning
# [INFO] Starting Stage 3: Test Generation for python project.
# [INFO] Saved generated test file to .../generated_tests/app/services/test_calculator_service.py
# [INFO] Starting Stage 4: Test Execution for python project.
# [INFO] Running command: pytest --cov=. --cov-report=xml generated_tests/
# [INFO] Stage 5: coverage=100%, target=90%. Target met.

# ==================================================
# KẾT QUẢ CUỐI CÙNG (FINAL SUMMARY)
# ==================================================
# Saved test plan to: ./demo_project/test_plan.json
# Saved coverage report to: ./demo_project/coverage_report.json
# Overall Coverage: 100.0%
# Tests Passed: 6/6
# Generated Test Files: 1
#   - generated_tests/app/services/test_calculator_service.py
```

---

*Tài liệu được tạo tự động từ phân tích toàn bộ source code tại https://github.com/anhluong447/90CovUnitest*
