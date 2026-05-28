# ARCHITECTURE.md — Unit Test Agent (90CovUnitest)

> **Mục đích của tài liệu này:** Hướng dẫn toàn diện cho AI Agent để nắm bắt hoàn toàn cấu trúc, luồng hoạt động, dữ liệu, và các quy ước lập trình của dự án `90CovUnitest`. Đọc hết tài liệu này trước khi thực hiện bất kỳ thay đổi nào.

---

## 1. Tổng quan hệ thống

**90CovUnitest** là một AI Agent tự động sinh unit test cho codebase Java (Spring Boot) và Python, với mục tiêu đạt **≥ 90% code coverage**. Hệ thống sử dụng kiến trúc **LangGraph State Machine** để điều phối pipeline gồm 5 giai đoạn tuần tự, có vòng lặp tự sửa lỗi (self-correction loop).

### Model LLM

Toàn bộ hệ thống hiện đã chuyển sang sử dụng **DeepSeek V4** qua OpenRouter. Không còn dùng Kimi K2.6.

| Stage | Model mặc định (config.yaml) | Fallback trong code |
|---|---|---|
| Stage 1 | `deepseek/deepseek-v4-flash` | `kimi/kimi-k2.6` (hardcode cũ trong `__init__`, chưa update) |
| Stage 2 | `deepseek/deepseek-v4-flash` | — |
| Stage 3 (primary) | `deepseek/deepseek-v4-flash` | — |
| Stage 3 (auto-fix fallback) | `deepseek/deepseek-v4-flash` | `deepseek/deepseek-v4-pro` |
| Stage 5 | `deepseek/deepseek-v4-flash` | `kimi/kimi-k2.6` (hardcode cũ, chưa update) |

> **Lưu ý:** Một số `__init__` method trong Stage classes vẫn hardcode fallback string `"kimi/kimi-k2.6"` nhưng thực tế model được lấy từ `config.yaml` — giá trị này chỉ là default khi key không tồn tại trong config.

### Hai chế độ vận hành

| Chế độ | Điều kiện | Mô tả |
|---|---|---|
| **LLM Mode** | `OPENROUTER_API_KEY` hợp lệ | Dùng DeepSeek V4 để phân tích và sinh test |
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
│   │   ├── stage1_analysis.py   # Phân tích cấu trúc code (heuristic scoring + LLM)
│   │   ├── stage2_planning.py   # Lập kế hoạch test cases
│   │   ├── stage3_generation.py # Sinh mã test + auto-fix loop
│   │   ├── stage4_execution.py  # Chạy pytest/Maven, đo coverage, auto-install deps
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
├── tests/                     # Unit tests cho chính Agent
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
    │   └── calculator_service.py
    └── generated_tests/       # Output sinh ra bởi Agent
        ├── app/services/test_calculator_service.py
        └── ISupport/core/
            ├── test_audio.py
            ├── test_llm.py
            └── test_stt.py
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
    service_files: List[str]              # Danh sách relative path các file được chọn để test
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
    │  Detect ngôn ngữ, heuristic scoring chọn file, parse AST, enrich bằng DeepSeek V4
    │  Output: state["analysis_result"], state["language"], state["service_files"]
    ▼
Stage 2: Test Planning          (stage2_planning.py)
    │  Dựa vào analysis_result, sinh test cases (happy/edge/error) bằng DeepSeek V4
    │  Output: state["test_plan"]
    ▼
Stage 3: Test Generation        (stage3_generation.py)
    │  Gọi DeepSeek V4 sinh code test, kiểm tra syntax, auto-fix tối đa 3 lần
    │  Output: state["generated_tests"], files trong {repo}/generated_tests/
    ▼
Stage 4: Test Execution         (stage4_execution.py)
    │  Auto-install deps, chạy pytest/Maven, parse coverage.xml hoặc jacoco.xml
    │  Output: state["coverage_report"]
    ▼
Stage 5: Self-Correction        (stage5_correction.py)
    │  Kiểm tra coverage >= target (90%)
    │  Nếu chưa đủ VÀ retry_count < max_retry (5):
    │      tăng retry_count, gọi DeepSeek V4 sinh test_plan mới → quay lại Stage 3
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

**Nhiệm vụ:** Phát hiện ngôn ngữ, **chọn lọc file đáng test bằng heuristic scoring**, parse AST, enrich bằng LLM.

#### 5.1 `detect_language_and_framework(repo_path)`

Quét file marker trong toàn bộ repo (bỏ qua `venv`, `.venv`, `node_modules`, `.git`, `build`, `target`, `frontend`, `front-end`, `ui`, `client`):

| Marker file | Kết quả |
|---|---|
| `pom.xml` | java / spring-boot / maven |
| `build.gradle` hoặc `build.gradle.kts` | java / spring-boot / gradle |
| `requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile` | python / fastapi / pip |
| `package.json` | typescript / nestjs / npm |

> **Thứ tự ưu tiên quan trọng:** Python check được thực hiện **trước** Node/TS check. Nếu repo có cả `requirements.txt` lẫn `package.json` (fullstack) → sẽ nhận diện là Python.

#### 5.2 `discover_service_files(repo_path, language)` — Heuristic Scoring

Đây là thay đổi lớn nhất so với phiên bản cũ. Không còn lọc cứng theo từ khóa "service" nữa.

**Bước 1 — Hard exclude** (loại bỏ ngay, không đọc nội dung):
- File bắt đầu bằng `test_`, kết thúc bằng `_test.py` / `Test.java` / `Tests.java`
- Tên file là: `conftest.py`, `setup.py`, `manage.py`, `wsgi.py`, `asgi.py`, `celery.py`
- Tên file bắt đầu bằng `__` (ví dụ `__init__.py`, `__main__.py`)
- Đường dẫn chứa thư mục trong `excluded_dirs`: `venv`, `.venv`, `.git`, `node_modules`, `build`, `target`, `tests`, `test`, `generated_tests`, `migrations`, `alembic`, `__pycache__`, `frontend`, `front-end`, `ui`, `client`

**Bước 2 — Scoring (0–100 điểm)**:

*Tên file / đường dẫn:*
- Chứa từ khóa dương (`service`, `handler`, `usecase`, `use_case`, `manager`, `repository`, `repo`, `controller`, `api`, `core`, `domain`, `business`, `logic`, `processor`, `worker`, `command`, `query`) → **+30 điểm**
- Chứa từ khóa âm (`config`, `settings`, `constant`, `enum`, `schema`, `migration`, `seed`, `fixture`) → **−50 điểm**

*Nội dung Python (qua `_score_python_content()`):*
- Có ít nhất 1 class với ≥ 2 method public (không bắt đầu bằng `_`) → **+40 điểm**
- `__init__` nhận tham số ngoài `self` (dependency injection) → **+10 điểm**
- Tổng `If + For + While + Try` ≥ 3 → **+20 điểm**
- Tất cả class là `@dataclass` hoặc `BaseModel` không có logic → **−40 điểm**
- Không có class nào VÀ số dòng < 50 → **−30 điểm**

*Nội dung Java (qua `_score_java_content()`):*
- Có annotation `@Service`, `@Component`, `@Repository`, `@RestController`, `@Controller`, `@UseCase` → **+40 điểm**
- Có ≥ 2 method public → **+30 điểm**
- Tổng methods + decision points ≥ 3 → **+20 điểm**
- Tất cả class là Lombok data class (`@Data`, `@Value`, `@Getter`, `@Setter`, ...) hoặc Record không có logic → **−40 điểm**
- Không có class nào VÀ số dòng < 50 → **−30 điểm**

**Bước 3 — Ngưỡng quyết định:**
- Điểm ≥ 40 → đưa vào danh sách
- Nếu rỗng → hạ ngưỡng xuống 20
- Nếu vẫn rỗng → lấy toàn bộ file đúng extension (không phải test file)

Log debug: `logger.debug(f"Score {score} — {rel_path}")`

#### 5.3 Parse + Enrich

Với mỗi file được chọn:
1. Chạy local AST parser (`JavaParser` hoặc `PythonParser`) → `local_parse`
2. Nếu có API key: gọi DeepSeek V4 với `STAGE1_USER_PROMPT_TEMPLATE`, enrich `local_parse`
3. Nếu không có API key: dùng trực tiếp `local_parse`
4. Sanitize qua `sanitize_service_metadata()`
5. Validate bằng `analysis_result.schema.json`

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

**Constraints quan trọng:**
- `priority` chỉ nhận: `"HIGH"` | `"MEDIUM"` | `"LOW"`
- `dependency.category` chỉ nhận: `"repository"` | `"http_client"` | `"message_queue"` | `"cache"` | `"service"` | `"utility"`

---

### Stage 2 — Test Planning (`stage2_planning.py`)

**Nhiệm vụ:** Từ `analysis_result`, sinh kế hoạch test cases.

**LLM mode:** Gọi DeepSeek V4 (`deepseek/deepseek-v4-flash`) với `STAGE2_USER_PROMPT_TEMPLATE`. Progress message: *"Đang chạy mô hình AI DeepSeek V4 để phác thảo các kịch bản kiểm thử..."*

**Local fallback:** `generate_local_fallback_plan()`:
- Skip method có `priority == "LOW"` và tên bắt đầu bằng `get/set/toString/hashCode/equals`
- Sinh tự động: 1 `happy_path` + 1 `edge_case` (nếu có params) + 1 `error_path` (nếu có throws hoặc dependencies) per method

**Sanitize bắt buộc trước validate:**
- `service`, `method`, `test_id`, `description`, `type` → convert sang `str`, `None` → `""`
- `mock.return_value` → `str`, `None` → `""`
- `input` values → `{k: str(v) if v is not None else "null"}`
- `expected.return_type` → `str`, `None` → `"void"`
- `expected.assertions` → `[str(a) for a in list if a is not None]`

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
      "setup": { "mocks": [] },
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

**LLM mode — `generate_llm_code_with_autofix()`:**
1. Gọi DeepSeek V4 (`deepseek/deepseek-v4-flash`) với system prompt + source code + test cases JSON, `temperature=0.1`
2. `extract_code_block()`: extract code từ response
3. `check_syntax()`: compile Python AST hoặc `javalang.parse.parse()`
4. Nếu lỗi: thêm error vào messages, gọi lại LLM (tối đa 3 lần auto-fix)
5. Từ lần thử thứ 2 trở đi (attempt >= 1): đổi sang model fallback `deepseek/deepseek-v4-pro` (từ config)

**`extract_code_block()` — 4 lớp fallback:**
1. Regex tìm ` ```lang ... ``` ` đóng mở hoàn chỉnh
2. Tìm unclosed code block (trường hợp LLM bị truncate)
3. Tìm dòng bắt đầu bằng `import`, `from`, `def`, `class`, `package`, `public class`, `@`
4. Last resort: trả về raw text nếu chứa `package`, `import`, hoặc `def test_`

**Mapping đường dẫn file test:**
- Python: `app/services/user_service.py` → `generated_tests/app/services/test_user_service.py`
- Java: `src/main/java/com/example/UserService.java` → `generated_tests/com/example/UserServiceTest.java` (strip prefix `src/main/java/`)

**Khi thất bại:** Ghi append vào `{repo_path}/failed_methods.log`

---

### Stage 4 — Test Execution (`stage4_execution.py`)

**Nhiệm vụ:** Thực thi test, đo coverage. Có **auto-install dependencies** mới.

#### Python execution

**Auto-install (mới):** Quét toàn bộ `requirements.txt` trong repo, cài từng package qua `pip install --no-cache-dir`. Bỏ qua package `pyaudiowpatch` (Windows-only).

**Tìm pytest executable** theo thứ tự (Linux/macOS trước, Windows sau):
```
{repo}/venv/bin/pytest
{repo}/.venv/bin/pytest
{repo}/backend/venv/bin/pytest
{repo}/backend/.venv/bin/pytest
{repo}/venv/Scripts/pytest.exe
{repo}/.venv/Scripts/pytest.exe
{repo}/backend/venv/Scripts/pytest.exe
{repo}/backend/.venv/Scripts/pytest.exe
```

**Lệnh chạy:**
```bash
pytest --cov=. --cov-report=xml {generated_test_files...}
```

**PYTHONPATH thông minh:** Thêm tất cả thư mục con có `.py` file vào `PYTHONPATH`, trừ các thư mục trong `excluded_dirs` và các thư mục có file trùng tên với stdlib Python (tránh shadowing).

**Parse `coverage.xml`:** Bỏ qua file test (`test_` trong tên), lấy `line-rate`, `branch-rate`, `uncovered_lines`. Parse `passed`/`failed` từ stdout pytest.

#### Java execution

Tìm `{repo}/target/site/jacoco/jacoco.xml`. Nếu tồn tại → parse. **Không tự chạy Maven** — cần chạy thủ công trước.

**Quan trọng:** Stage 4 **THROW RuntimeError** nếu test execution thất bại — không có silent failure.

---

### Stage 5 — Self-Correction (`stage5_correction.py`)

**Logic:**
```
if current_coverage >= target_coverage:  → END (thành công)
if retry_count >= max_retry (5):          → END (đã hết retry)
else:
    retry_count += 1
    Gọi DeepSeek V4 với test_plan + coverage_report
    LLM sinh test_plan mới bổ sung test cases nhắm vào uncovered_lines
    state["test_plan"] = updated_plan
    → Graph routing quay lại Stage 3
```

**Không có local fallback** cho Stage 5 — nếu không có API key sẽ **THROW RuntimeError**.

---

## 6. LLM Client (`agent/llm/client.py`)

### `OpenRouterClient`

```python
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY") or "mock-key"
)
```

**Retry logic:** 3 lần, exponential backoff (2s → 4s → 8s)

**Headers bắt buộc:**
```python
extra_headers = {
    "HTTP-Referer": "https://github.com/anhluong447/90CovUnitest",
    "X-Title": "Unit Test Agent"
}
```

**`max_tokens`:** 4096 (cố định trong tất cả request)

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

Tất cả prompts đều được viết bằng **tiếng Việt**.

| Prompt | Stage | Model | Định dạng output |
|---|---|---|---|
| `STAGE1_SYSTEM_PROMPT` + `STAGE1_USER_PROMPT_TEMPLATE` | Stage 1 | DeepSeek V4 Flash | JSON Object (service metadata) |
| `STAGE2_SYSTEM_PROMPT` + `STAGE2_USER_PROMPT_TEMPLATE` | Stage 2 | DeepSeek V4 Flash | JSON Object (test_plan) |
| `STAGE3_SYSTEM_PROMPT_JAVA` | Stage 3 | DeepSeek V4 Flash | Code block ` ```java ` |
| `STAGE3_SYSTEM_PROMPT_PYTHON` | Stage 3 | DeepSeek V4 Flash | Code block ` ```python ` |
| `STAGE3_USER_PROMPT_TEMPLATE` | Stage 3 | — | — |
| `STAGE3_AUTO_FIX_PROMPT` | Stage 3 (retry) | DeepSeek V4 Pro | Code block ` ```... ` |
| `STAGE5_SYSTEM_PROMPT` + `STAGE5_USER_PROMPT_TEMPLATE` | Stage 5 | DeepSeek V4 Flash | JSON Object (updated test_plan) |

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
runs_db[run_id] = {
    "run_id": str,
    "repo_path": str,
    "status": "running" | "awaiting_user_approval" | "completed" | "failed",
    "logs": List[str],
    "test_plan": Dict,
    "coverage_report": Dict,
    "history": List[str],
    "generated_files": List[{"path": str, "content": str}],
    "progress": {
        "stage": int,            # Stage hiện tại (1-5)
        "percentage": int,       # 0-100
        "message": str,
        "status": str,
        "stage_data": Dict
    },
    "error": str | None
    # Lưu ý: "agent_state" snapshot không còn trong schema mặc định của run
}
```

### API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/run` | Bắt đầu Phase 1. Body: `{"repo_path": "..."}` |
| `POST` | `/api/resume/{run_id}` | Bắt đầu Phase 2. Body: `{"selected_test_ids": [...]}` |
| `GET` | `/api/status/{run_id}` | Lấy toàn bộ trạng thái của run |
| `GET` | `/api/runs` | Liệt kê tất cả runs |
| `GET` | `/api/list-dirs` | Duyệt thư mục server (base `/app`). Ẩn: `venv`, `.venv`, `node_modules`, `static`, `agent`, `schemas`, `tests`, `__pycache__`, `.git`, `.github`, `.pytest_cache` |
| `GET` | `/` | Serve `static/index.html` |

### Progress tracking (`agent/progress.py`)

```python
current_run_id = contextvars.ContextVar("current_run_id", default=None)

def update_progress(stage, percentage, message, stage_data=None):
    run_id = current_run_id.get()
    # Cập nhật runs_db[run_id]["progress"]
```

Mỗi background thread set `current_run_id` trước khi chạy và `reset()` trong `finally`.

**Quan trọng:** `runs_db` là dict in-memory — restart server sẽ mất toàn bộ history.

---

## 10. Configuration (`config.yaml`)

```yaml
models:
  stage1: "deepseek/deepseek-v4-flash"
  stage2: "deepseek/deepseek-v4-flash"
  stage3: "deepseek/deepseek-v4-flash"
  stage3_fallback: "deepseek/deepseek-v4-flash"
  stage5: "deepseek/deepseek-v4-flash"
  retry: "deepseek/deepseek-v4-flash"

coverage:
  line_threshold: 90
  branch_threshold: 80
  max_retries: 5        # Tăng từ 3 lên 5

execution:
  timeout_seconds: 600
  docker_memory_limit: "4g"
  docker_cpu_limit: 2

mutation:
  enabled: false
  score_threshold: 70
```

---

## 11. JSON Schemas (`schemas/`)

### `analysis_result.schema.json`

**Enum constraints:**
- `method.priority`: `["HIGH", "MEDIUM", "LOW"]`
- `dependency.category`: `["repository", "http_client", "message_queue", "cache", "service", "utility"]`

### `test_plan.schema.json`

**Enum constraints:**
- `test_case.type`: `["happy_path", "edge_case", "error_path", "business"]`
- `mock.behavior`: `["return", "throw", "do_nothing"]`
- `input` và `mock.return_value`: **phải là `string`** — Stage 2 tự động convert

### `coverage_report.schema.json`

**Required fields:** `total_coverage` (number), `summary` (total_tests, passed, failed, skipped), `classes` (dict), `failures[]`

---

## 12. Quy ước code và các pattern quan trọng

### Pattern 1: Stage Class Structure

```python
class StageN:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_client = OpenRouterClient()
        self.model = config.get("models", {}).get("stageN", "deepseek/deepseek-v4-flash")

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

---

## 13. Các điểm cần chú ý khi sửa code

1. **Thêm language mới:** Cần sửa `detect_language_and_framework()`, hard exclude và scoring logic trong `discover_service_files()`, thêm `_score_{language}_content()` method, `generate_local_fallback_code()`, thêm parser mới trong `parsers/`, thêm system prompt trong `prompts.py`.

2. **Thứ tự detect ngôn ngữ:** Python check hiện ở **trước** Node/TS check trong `detect_language_and_framework()`. Fullstack repo có cả `requirements.txt` + `package.json` sẽ được nhận diện là Python.

3. **Thay đổi scoring threshold:** Logic ngưỡng 40/20 nằm trong `discover_service_files()`. Thay đổi cần test kỹ để không bỏ sót file hoặc chọn thừa.

4. **Auto-install trong Stage 4:** Stage 4 cài tất cả package từ mọi `requirements.txt` tìm thấy trong repo. Nếu repo có package nặng (torch, tensorflow) sẽ rất chậm. Cần thêm blacklist nếu cần tối ưu tốc độ.

5. **Stage 4 Java không tự chạy Maven:** Chỉ đọc `jacoco.xml` có sẵn. Cần cải thiện nếu muốn tích hợp CI/CD đầy đủ.

6. **`failed_methods.log` không tự clear:** Ghi append giữa các run. Cần xóa thủ công hoặc thêm logic clear khi bắt đầu run mới.

7. **`runs_db` là in-memory, không thread-safe:** FastAPI Background Tasks chạy trong thread pool — có thể race condition nếu nhiều runs cùng lúc sửa cùng `run_id`. Cần Redis/lock nếu scale.

8. **Model string fallback không đồng bộ:** Một số `__init__` hardcode `"kimi/kimi-k2.6"` làm default string khi config key không tồn tại. Thực tế tất cả key đã có trong `config.yaml` nên không ảnh hưởng runtime, nhưng cần cập nhật để tránh nhầm lẫn.

---

## 14. Ví dụ chạy và kết quả mong đợi

```bash
$ python main.py --repo ./demo_project

# [INFO] Detected: language=python, framework=fastapi, build_tool=pip
# [DEBUG] Score 70 — app/services/calculator_service.py   ← heuristic scoring
# [INFO] Discovered 1 service files to analyze.
# [INFO] Starting Stage 2: Test Planning
# [INFO] Đang chạy mô hình AI DeepSeek V4 để phác thảo các kịch bản kiểm thử...
# [INFO] Starting Stage 3: Test Generation for python project.
# [INFO] Saved generated test file to .../generated_tests/app/services/test_calculator_service.py
# [INFO] Installing project dependencies from .../requirements.txt...
# [INFO] Running command: pytest --cov=. --cov-report=xml generated_tests/...
# [INFO] Stage 5: coverage=100%, target=90%. Target met.

# ==================================================
# KẾT QUẢ CUỐI CÙNG
# ==================================================
# Overall Coverage: 100.0%
# Tests Passed: 6/6
# Generated Test Files: 1
#   - generated_tests/app/services/test_calculator_service.py
```

---

*Tài liệu được cập nhật từ commit `5489d9c` — https://github.com/anhluong447/90CovUnitest*
ENDOFFILE
