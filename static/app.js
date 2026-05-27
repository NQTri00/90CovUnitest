let currentRunId = null;
let pollInterval = null;
let currentFiles = [];

// Window management: Drag-and-drop mechanics
let activeWindow = null;
let dragOffsetX = 0;
let dragOffsetY = 0;
let windowZIndex = 50;

function focusWindow(windowId, e) {
    const win = document.getElementById(windowId);
    if (!win) return;
    
    // Bring window to front
    windowZIndex += 1;
    win.style.zIndex = windowZIndex;
    
    // Update active state class on windows
    document.querySelectorAll('.retro-window').forEach(w => {
        w.classList.remove('window-active');
    });
    win.classList.add('window-active');

    // Update taskbar tab active state
    document.querySelectorAll('.taskbar-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    const tabBtn = document.getElementById(`tab-btn-${windowId}`);
    if (tabBtn) {
        tabBtn.classList.add('active');
        tabBtn.style.display = 'flex'; // Ensure visible if hidden
    }
}

// Drag & drop logic
document.addEventListener('mousedown', function(e) {
    const header = e.target.closest('.window-header');
    if (!header) return;
    
    const win = header.closest('.retro-window');
    if (!win) return;
    
    activeWindow = win;
    focusWindow(win.id, e);
    
    const rect = win.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    
    win.classList.add('dragging');
    e.preventDefault();
});

document.addEventListener('mousemove', function(e) {
    if (!activeWindow) return;
    
    // Calculate new position relative to viewport
    let left = e.clientX - dragOffsetX;
    let top = e.clientY - dragOffsetY;
    
    // Keep window within reasonable bounds
    const minVisibleX = 50; // border decoration offset
    const maxVisibleX = window.innerWidth - 100;
    const minVisibleY = 0;
    const maxVisibleY = window.innerHeight - 80;
    
    left = Math.max(minVisibleX, Math.min(left, maxVisibleX));
    top = Math.max(minVisibleY, Math.min(top, maxVisibleY));
    
    activeWindow.style.left = left + 'px';
    activeWindow.style.top = top + 'px';
});

document.addEventListener('mouseup', function() {
    if (activeWindow) {
        activeWindow.classList.remove('dragging');
        activeWindow = null;
    }
});

// Minimize/Maximize/Close helper functions
function minimizeWindow(windowId) {
    const win = document.getElementById(windowId);
    if (!win) return;
    win.style.display = 'none';
    
    // De-activate tab in taskbar
    const tabBtn = document.getElementById(`tab-btn-${windowId}`);
    if (tabBtn) {
        tabBtn.classList.remove('active');
    }
}

function closeWindow(windowId) {
    minimizeWindow(windowId);
}

function maximizeWindow(windowId) {
    const win = document.getElementById(windowId);
    if (!win) return;
    
    if (win.style.width === '100vw') {
        // Restore standard layout sizes
        if (windowId === 'window-haishin') {
            win.style.width = '780px';
            win.style.height = '520px';
        } else if (windowId === 'window-codeexplorer') {
            win.style.width = '850px';
            win.style.height = '560px';
        } else if (windowId === 'window-settings') {
            win.style.width = '440px';
            win.style.height = '420px';
        } else if (windowId === 'window-webcam') {
            win.style.width = '380px';
            win.style.height = '280px';
        }
        win.style.top = '100px';
        win.style.left = '200px';
    } else {
        // Maximize to workspace
        win.style.width = '100vw';
        win.style.height = 'calc(100vh - 40px)';
        win.style.top = '0';
        win.style.left = '0';
    }
}

function toggleWindow(windowId) {
    const win = document.getElementById(windowId);
    if (!win) return;
    
    const tabBtn = document.getElementById(`tab-btn-${windowId}`);
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        focusWindow(windowId);
        if (tabBtn) {
            tabBtn.style.display = 'flex';
            tabBtn.classList.add('active');
        }
    } else {
        win.style.display = 'none';
        if (tabBtn) {
            tabBtn.classList.remove('active');
        }
    }
}

// Start menu toggle
function toggleStartMenu() {
    const menu = document.getElementById('startMenu');
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
}

// Close start menu when clicking outside
document.addEventListener('click', function(e) {
    const menu = document.getElementById('startMenu');
    const startBtn = document.querySelector('.start-btn');
    if (menu && menu.style.display === 'flex') {
        if (!menu.contains(e.target) && !startBtn.contains(e.target)) {
            menu.style.display = 'none';
        }
    }
});

// Speak Bubble Popup
function closePopup() {
    const popup = document.getElementById('os-popup');
    popup.style.display = 'none';
}

function openHelp() {
    alert("KAngel Unit Test Agent OS v1.0\nDouble-click or click shortcuts to control window elements.\nRun settings configurations to start running unit tests automatically! ♡");
}

// Log formatting to livestream Chat Messages
const viewerUsernames = [
    "chiba_otaku", "tenshi_kangel", "cyber_girl99", "kangel_love", 
    "mega_neko", "blue_pill", "weeb_guy", "dusk_devil", "sweet_candy"
];

const usernameColors = [
    "#ff4d6d", // pink
    "#7c61a5", // purple
    "#00b894", // green
    "#0984e3", // blue
    "#fdcb6e", // yellow
    "#e84393", // magenta
    "#00cec9", // cyan
    "#6c5ce7", // violet
    "#d63031"  // red
];

function getUsernameColor(username) {
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
        hash = username.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % usernameColors.length;
    return usernameColors[index];
}

function formatLogLineToChat(logText) {
    // Generate a random viewer name
    const username = viewerUsernames[Math.floor(Math.random() * viewerUsernames.length)];
    
    // Parse the log type
    let cleanText = logText;
    // Strip timestamps like 2026-05-26 15:30:00,123 [INFO]
    cleanText = cleanText.replace(/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}(?:,\d+)?\s\[[A-Z]+\]\s/, "");
    
    // Determine the style class
    let styleClass = "";
    let prefix = "";
    let isKAngel = false;
    let isSystem = false;
    let isError = false;
    
    if (logText.includes("[ERROR]")) {
        styleClass = "error-line";
        prefix = `⚠️ WARNING_BOT`;
        cleanText = `Lỗi hệ thống nè! -> ${cleanText} 💔`;
        isError = true;
    } else if (logText.includes("[WARNING]")) {
        styleClass = "system-line";
        prefix = `📢 SYSTEM`;
        cleanText = `Chú ý nha: ${cleanText} ✿`;
        isSystem = true;
    } else if (logText.includes("Starting Phase") || logText.includes("resuming Phase") || logText.includes("Agent hoàn thành")) {
        styleClass = "system-line";
        prefix = `💜 KAngel`;
        cleanText = `✨ ${cleanText} ✨`;
        isKAngel = true;
    } else {
        prefix = username;
        // Randomly beautify standard info logs as chat messages
        const expressions = ["chạy ngay đi~", "cute xỉu", "bless KAngel 🙏", "tiếp đi mà", "sinh test kìa! 🚀", "♡", "✿"];
        const exp = expressions[Math.floor(Math.random() * expressions.length)];
        cleanText = `${cleanText} (${exp})`;
    }
    
    const div = document.createElement("div");
    div.className = `log-line ${styleClass}`;
    
    const prefixSpan = document.createElement("span");
    prefixSpan.className = "chat-username";
    
    if (isKAngel) {
        prefixSpan.className = "chat-username kangel-badge";
        prefixSpan.innerHTML = `👑 KAngel: `;
    } else if (isSystem) {
        prefixSpan.className = "chat-username system-badge";
        prefixSpan.innerText = `${prefix}: `;
    } else if (isError) {
        prefixSpan.className = "chat-username error-badge";
        prefixSpan.innerText = `${prefix}: `;
    } else {
        prefixSpan.innerText = `${prefix}: `;
        prefixSpan.style.color = getUsernameColor(prefix);
    }
    
    div.appendChild(prefixSpan);
    
    const textSpan = document.createElement("span");
    textSpan.className = "chat-message-text";
    textSpan.innerText = cleanText;
    div.appendChild(textSpan);
    
    return div;
}

function setButtonsRunningState(isRunning) {
    const btnRun = document.getElementById("btnRun");
    const btnCloneRun = document.getElementById("btnCloneRun");
    if (isRunning) {
        if (btnRun) {
            btnRun.disabled = true;
            btnRun.innerText = "Đang chạy...";
        }
        if (btnCloneRun) {
            btnCloneRun.disabled = true;
            btnCloneRun.innerText = "Đang chạy...";
        }
    } else {
        if (btnRun) {
            btnRun.disabled = false;
            btnRun.innerText = "Khởi chạy";
        }
        if (btnCloneRun) {
            btnCloneRun.disabled = false;
            btnCloneRun.innerText = "Clone & Khởi chạy";
        }
    }
}

async function startGithubCloneRun() {
    const githubUrl = document.getElementById("githubUrl").value.trim();
    if (!githubUrl) {
        alert("Vui lòng nhập đường dẫn GitHub Repository!");
        return;
    }
    
    // Set repoPath input value to the Github URL so that the rest of the application is aware
    document.getElementById("repoPath").value = githubUrl;
    
    // Now trigger startAgentRun
    await startAgentRun();
}

// Agent Core functions mapped to UI elements
async function startAgentRun() {
    const repoPath = document.getElementById("repoPath").value.trim();
    if (!repoPath) {
        alert("Vui lòng nhập đường dẫn repository!");
        return;
    }

    // Reset UI
    setButtonsRunningState(true);
    
    // Hide results window and selector window
    document.getElementById("window-codeexplorer").style.display = "none";
    document.getElementById("tab-btn-window-codeexplorer").style.display = "none";
    document.getElementById("selectionPanel").style.display = "none";
    
    // Reset Task Manager progress
    document.getElementById("progressContainer").style.display = "block";
    document.getElementById("progressBarFill").style.width = "0%";
    document.getElementById("progressPercent").innerText = "0%";
    document.getElementById("progressMessage").innerText = "Đang kết nối...";
    
    // Reset metrics
    document.getElementById("displayFollowers").innerText = "0%";
    document.getElementById("displayMental").innerText = "STARTING";
    document.getElementById("displayStress").innerText = "0";
    document.getElementById("displayAffection").innerText = "---";
    
    const terminal = document.getElementById("terminalLogs");
    terminal.dataset.serverLogCount = "0";
    terminal.innerHTML = '<div class="log-line system-line"><span class="chat-username system-badge">📢 SYSTEM: </span><span class="chat-message-text">Đang gửi yêu cầu khởi chạy Agent tới API...</span></div>';
    
    resetStepper();
    updateStatusBadge("Running", "running");

    try {
        const response = await fetch("/api/run", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ repo_path: repoPath })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Không thể khởi chạy Agent.");
        }

        const data = await response.json();
        currentRunId = data.run_id;
        
        appendTerminalLog(`> Đã khởi tạo tiến trình. Run ID: ${currentRunId}`, "system-line");

        // Start polling
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(pollStatus, 1000);

    } catch (error) {
        appendTerminalLog(`> Lỗi: ${error.message}`, "error-line");
        setButtonsRunningState(false);
        updateStatusBadge("Failed", "failed");
        document.getElementById("displayMental").innerText = "FAILED";
    }
}

async function pollStatus() {
    if (!currentRunId) return;

    try {
        const response = await fetch(`/api/status/${currentRunId}`);
        if (!response.ok) throw new Error("Lỗi kết nối tới máy chủ.");
        
        const data = await response.json();
        
        // Update Stream Timeline / Video progress bar as a visual indicator
        const streamTimeline = document.getElementById("streamTimeline");
        if (data.progress && streamTimeline) {
            streamTimeline.style.width = `${data.progress.percentage}%`;
        }

        // Update Terminal Logs in Chat layout
        renderLogs(data.logs);

        // Update Progress Bar inside Task Manager
        showProgressBar(data.progress);

        // Update Stepper steps
        updateStepperStateFromProgress(data.progress, data.status);

        // Map live metrics to Task Manager boxes
        updateTaskManagerMetrics(data);

        // Update badge status
        if (data.status === "awaiting_user_approval") {
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = null;
            updateStatusBadge("Awaiting Approval", "awaiting");
            
            // Show selection window & focus
            const selectionPanel = document.getElementById("selectionPanel");
            selectionPanel.style.display = "flex";
            focusWindow("selectionPanel");
            
            renderTestCaseSelector(data.test_plan);
            
            appendTerminalLog("> Đã chuẩn bị xong kế hoạch kiểm thử. Vui lòng chọn kịch bản kiểm thử.", "system-line");
            return;
        }

        if (data.status === "completed") {
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = null;
            updateStatusBadge("Completed", "completed");
            setButtonsRunningState(false);
            
            appendTerminalLog("> Agent hoàn thành toàn bộ quy trình thành công!", "system-line");
            
            // Pop open results explorer window & focus
            const explorerWin = document.getElementById("window-codeexplorer");
            explorerWin.style.display = "flex";
            focusWindow("window-codeexplorer");
            
            showDashboard(data);
            
            // Hide progress container inside task manager
            document.getElementById("progressContainer").style.display = "none";
        } else if (data.status === "failed") {
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = null;
            updateStatusBadge("Failed", "failed");
            setButtonsRunningState(false);
            
            appendTerminalLog(`> Tiến trình thất bại: ${data.error || "Không rõ nguyên nhân"}`, "error-line");
            document.getElementById("progressContainer").style.display = "none";
        } else {
            updateStatusBadge("Running", "running");
        }

    } catch (error) {
        console.error(error);
        appendTerminalLog(`> Lỗi polling status: ${error.message}`, "error-line");
    }
}

function updateStatusBadge(text, className) {
    const badge = document.getElementById("runStatus");
    if (!badge) return;
    badge.innerText = text;
    badge.className = `status-badge ${className}`;
}

function resetStepper() {
    const steps = ["stage1", "stage2", "stage3", "stage4", "stage5"];
    steps.forEach(s => {
        const el = document.getElementById(`step-${s}`);
        if (el) el.className = "step";
    });
}

function updateStepperStateFromProgress(progress, status) {
    const steps = {
        1: document.getElementById("step-stage1"),
        2: document.getElementById("step-stage2"),
        3: document.getElementById("step-stage3"),
        4: document.getElementById("step-stage4"),
        5: document.getElementById("step-stage5"),
    };

    const currentStage = (progress && progress.stage) ? progress.stage : 1;

    for (let s = 1; s <= 5; s++) {
        const el = steps[s];
        if (!el) continue;

        if (s < currentStage) {
            el.className = "step success";
        } else if (s === currentStage) {
            if (status === "awaiting_user_approval") {
                el.className = "step success";
            } else if (status === "completed") {
                el.className = "step success";
            } else if (status === "failed") {
                el.className = "step failed";
            } else {
                el.className = "step active";
            }
        } else {
            el.className = "step";
        }
    }

    if (status === "completed") {
        for (let s = 1; s <= 5; s++) {
            if (steps[s]) steps[s].className = "step success";
        }
    }
}

// Update Task Manager metrics based on progress data
function updateTaskManagerMetrics(data) {
    const displayFollowers = document.getElementById("displayFollowers");
    const displayMental = document.getElementById("displayMental");
    const displayStress = document.getElementById("displayStress");
    const displayAffection = document.getElementById("displayAffection");
    
    // Followers -> maps to Coverage % or progress percentage
    let coverage = 0;
    if (data.coverage_report && data.coverage_report.total_coverage !== undefined) {
        coverage = data.coverage_report.total_coverage;
    } else if (data.progress && data.progress.stage_data && data.progress.stage_data.coverage) {
        coverage = data.progress.stage_data.coverage.total_coverage;
    }
    
    if (coverage > 0) {
        displayFollowers.innerText = `${coverage}%`;
    } else if (data.progress) {
        displayFollowers.innerText = `${data.progress.percentage}%`;
    } else {
        displayFollowers.innerText = "0%";
    }
    
    // Mental Status -> Stage state (Planning, Generating, Correcting, Completed, Awaiting, On the brink)
    if (data.status === "awaiting_user_approval") {
        displayMental.innerText = "AWAITING";
    } else if (data.status === "completed") {
        displayMental.innerText = "STABLE";
    } else if (data.status === "failed") {
        displayMental.innerText = "MELTDOWN";
    } else if (data.progress) {
        const stagesMap = {
            1: "ANALYSIS",
            2: "PLANNING",
            3: "GENERATION",
            4: "EXECUTION",
            5: "CORRECTION"
        };
        displayMental.innerText = stagesMap[data.progress.stage] || "RUNNING";
    } else {
        displayMental.innerText = "IDLE";
    }
    
    // Stress -> Failed tests count or retry loops
    let failedCount = 0;
    if (data.progress && data.progress.stage === 5 && data.progress.stage_data && data.progress.stage_data.failed_tests_count !== undefined) {
        failedCount = data.progress.stage_data.failed_tests_count;
    } else if (data.coverage_report && data.coverage_report.summary && data.coverage_report.summary.failed !== undefined) {
        failedCount = data.coverage_report.summary.failed;
    }
    displayStress.innerText = failedCount;
    
    // Affection -> Passed tests count
    let passedCount = "0";
    if (data.coverage_report && data.coverage_report.summary && data.coverage_report.summary.passed !== undefined) {
        passedCount = `${data.coverage_report.summary.passed}/${data.coverage_report.summary.total_tests}`;
    } else if (data.status === "completed") {
        passedCount = "MAX";
    } else {
        passedCount = "---";
    }
    displayAffection.innerText = passedCount;
}

function renderLogs(logsList) {
    const terminal = document.getElementById("terminalLogs");
    if (!terminal) return;
    
    const currentServerCount = parseInt(terminal.dataset.serverLogCount || "0");
    if (currentServerCount === logsList.length) {
        return;
    }
    
    if (logsList.length < currentServerCount) {
        terminal.innerHTML = "";
        terminal.dataset.serverLogCount = "0";
    }
    
    const startIdx = parseInt(terminal.dataset.serverLogCount || "0");
    for (let i = startIdx; i < logsList.length; i++) {
        const div = formatLogLineToChat(logsList[i]);
        terminal.appendChild(div);
    }
    
    terminal.dataset.serverLogCount = logsList.length;
    terminal.scrollTop = terminal.scrollHeight;
}

function appendTerminalLog(message, className = "") {
    const terminal = document.getElementById("terminalLogs");
    if (!terminal) return;
    
    const div = document.createElement("div");
    div.className = `log-line ${className}`;
    
    const prefixSpan = document.createElement("span");
    prefixSpan.className = "chat-username kangel-badge";
    prefixSpan.innerHTML = `👑 KAngel: `;
    div.appendChild(prefixSpan);
    
    const textSpan = document.createElement("span");
    textSpan.className = "chat-message-text";
    textSpan.innerText = message;
    div.appendChild(textSpan);
    
    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

function showDashboard(data) {
    const dashboard = document.getElementById("dashboardArea");
    if (!dashboard) return;
    dashboard.style.display = "block";

    // 1. Coverage Circle
    const cov = data.coverage_report?.total_coverage || 0;
    document.getElementById("coverageValue").innerText = `${cov}%`;
    
    const ring = document.getElementById("coverageRing");
    if (ring) {
        const circumference = 263.89; // 2 * pi * 42
        const offset = circumference - (circumference * cov / 100);
        ring.style.strokeDashoffset = offset;

        // Red if below target, green if met
        const target = parseFloat(data.test_plan?.target_coverage || 90.0);
        if (cov < target) {
            ring.style.stroke = "var(--pink)";
        } else {
            ring.style.stroke = "#20bf6b";
        }
    }

    // 2. Test count
    const cases = data.test_plan?.test_cases || [];
    const totalCountEl = document.getElementById("totalTestCases");
    if (totalCountEl) totalCountEl.innerText = cases.length;

    // 3. Execution Pass / Total
    const passed = cases.length; // Mock or total test cases
    const execResEl = document.getElementById("testExecutionResult");
    if (execResEl) execResEl.innerText = `${passed}/${cases.length}`;

    // 4. Populate test plan table
    const tableBody = document.getElementById("testPlanTableBody");
    if (tableBody) {
        tableBody.innerHTML = "";
        if (cases.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center;">Không tìm thấy kế hoạch test case.</td></tr>';
        } else {
            cases.forEach(c => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(c.service || "N/A")}</strong></td>
                    <td><code>${escapeHtml(c.method || "N/A")}</code></td>
                    <td><small>${escapeHtml(c.test_id || "N/A")}</small></td>
                    <td><span class="badge ${c.type || ''}">${escapeHtml(c.type || "N/A")}</span></td>
                    <td>${escapeHtml(c.description || "")}</td>
                `;
                tableBody.appendChild(tr);
            });
        }
    }

    // 5. Code Viewer Files List
    const filesList = document.getElementById("generatedFilesList");
    if (filesList) {
        filesList.innerHTML = "";
        currentFiles = data.generated_files || [];

        if (currentFiles.length === 0) {
            filesList.innerHTML = '<div style="padding: 1rem; color: #888; text-align: center;">Không có tệp test được sinh.</div>';
            document.getElementById("currentFilePath").innerText = "Select a file";
            document.getElementById("codeArea").innerText = "# No files available";
        } else {
            currentFiles.forEach((file, index) => {
                const div = document.createElement("div");
                div.className = `file-item ${index === 0 ? 'active' : ''}`;
                div.innerText = file.path.split(/[\\/]/).pop(); // Get filename only
                div.title = file.path;
                div.onclick = () => selectFile(index);
                filesList.appendChild(div);
            });

            // Show first file by default
            selectFile(0);
        }
    }
}

function selectFile(index) {
    if (index < 0 || index >= currentFiles.length) return;

    // Update active class in sidebar list
    const fileItems = document.querySelectorAll(".file-item");
    fileItems.forEach((el, idx) => {
        if (idx === index) el.classList.add("active");
        else el.classList.remove("active");
    });

    const file = currentFiles[index];
    document.getElementById("currentFilePath").innerText = file.path;
    
    const codeArea = document.getElementById("codeArea");
    codeArea.innerText = file.content;

    // Detect language from extension
    const ext = file.path.split('.').pop().toLowerCase();
    if (ext === 'java') {
        codeArea.className = "language-java";
    } else {
        codeArea.className = "language-python";
    }

    // Trigger Prism highlight
    Prism.highlightElement(codeArea);
}

function copyCodeToClipboard() {
    const code = document.getElementById("codeArea").innerText;
    navigator.clipboard.writeText(code).then(() => {
        alert("Đã sao chép mã nguồn kiểm thử vào clipboard!");
    }).catch(err => {
        console.error("Copy failed", err);
    });
}

function switchTab(tabId) {
    const buttons = document.querySelectorAll(".tab-btn");
    const contents = document.querySelectorAll(".tab-content");

    buttons.forEach(btn => {
        if (btn.getAttribute("onclick").includes(tabId)) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    contents.forEach(content => {
        if (content.id === tabId) {
            content.classList.add("active");
        } else {
            content.classList.remove("active");
        }
    });
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#039;");
}

let currentBrowsingPath = "";

function toggleDirBrowser(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("dirBrowserDropdown");
    const isHidden = dropdown.style.display === "none";
    
    if (isHidden) {
        dropdown.style.display = "block";
        loadDirectories(currentBrowsingPath);
    } else {
        dropdown.style.display = "none";
    }
}

async function loadDirectories(path) {
    const listContainer = document.getElementById("browserDirList");
    listContainer.innerHTML = '<div style="padding: 10px; color: #888; text-align: center;">Đang tải...</div>';
    
    try {
        const response = await fetch(`/api/list-dirs?path=${encodeURIComponent(path)}`);
        if (!response.ok) throw new Error("Không thể tải danh sách thư mục");
        
        const data = await response.json();
        currentBrowsingPath = data.current_path;
        
        document.getElementById("currentBrowsingPath").innerText = currentBrowsingPath ? `/app/${currentBrowsingPath}` : "/app";
        document.getElementById("btnDirUp").disabled = currentBrowsingPath === "";
        
        listContainer.innerHTML = "";
        
        if (data.directories.length === 0) {
            listContainer.innerHTML = '<div style="padding: 10px; color: #888; text-align: center;">Thư mục trống hoặc không có thư mục con hợp lệ.</div>';
            return;
        }
        
        data.directories.forEach(dir => {
            const item = document.createElement("div");
            item.className = "dir-item";
            item.innerHTML = `<span class="icon">📁</span> <span class="name">${escapeHtml(dir)}</span>`;
            
            // Double click to enter folder
            item.ondblclick = (e) => {
                e.stopPropagation();
                const newPath = currentBrowsingPath ? `${currentBrowsingPath}/${dir}` : dir;
                document.getElementById("repoPath").value = newPath;
                loadDirectories(newPath);
            };
            
            // Single click to select
            item.onclick = (e) => {
                e.stopPropagation();
                const selectedPath = currentBrowsingPath ? `${currentBrowsingPath}/${dir}` : dir;
                document.getElementById("repoPath").value = selectedPath;
                
                // Highlight item
                document.querySelectorAll(".dir-item").forEach(el => el.style.background = "");
                item.style.background = "rgba(124, 97, 165, 0.18)";
            };
            
            listContainer.appendChild(item);
        });
        
    } catch (err) {
        listContainer.innerHTML = `<div style="padding: 10px; color: var(--pink); text-align: center;">Lỗi: ${err.message}</div>`;
    }
}

function navigateUpDir(event) {
    if (event) event.stopPropagation();
    if (!currentBrowsingPath) return;
    
    const parts = currentBrowsingPath.split("/");
    parts.pop();
    const parentPath = parts.join("/");
    
    document.getElementById("repoPath").value = parentPath || "demo_project";
    loadDirectories(parentPath);
}

// Close dropdown when clicking outside
document.addEventListener("click", function(e) {
    const dropdown = document.getElementById("dirBrowserDropdown");
    const selectWrapper = document.querySelector(".select-wrapper");
    
    if (dropdown && dropdown.style.display !== "none") {
        if (!dropdown.contains(e.target) && !selectWrapper.contains(e.target)) {
            dropdown.style.display = "none";
        }
    }
});

function showProgressBar(progress) {
    const container = document.getElementById("progressContainer");
    if (!progress) {
        container.style.display = "none";
        return;
    }
    
    container.style.display = "block";
    
    const fill = document.getElementById("progressBarFill");
    const percent = document.getElementById("progressPercent");
    const msg = document.getElementById("progressMessage");
    const subDetail = document.getElementById("progressSubDetail");
    
    if (fill) fill.style.width = `${progress.percentage}%`;
    if (percent) percent.innerText = `${progress.percentage}%`;
    if (msg) msg.innerText = progress.message || "Đang xử lý...";
    
    // Show additional stage details if present
    if (progress.stage_data && subDetail) {
        let details = "";
        if (progress.stage === 1 && progress.stage_data.service_files) {
            details = `Tổng số file cần quét: ${progress.stage_data.service_files.length}`;
            if (progress.stage_data.analyzing_file) {
                details += ` | Đang phân tích: ${progress.stage_data.analyzing_file}`;
            }
        } else if (progress.stage === 3) {
            if (progress.stage_data.generating_service) {
                details = `Đang xử lý dịch vụ: ${progress.stage_data.generating_service}`;
            }
            if (progress.stage_data.generated_files) {
                details += ` | Đã sinh xong: ${progress.stage_data.generated_files.length} file`;
            }
        } else if (progress.stage === 4 && progress.stage_data.coverage) {
            const cov = progress.stage_data.coverage;
            details = `Độ bao phủ hiện tại: ${cov.total_coverage}% | Số file test: ${cov.files ? Object.keys(cov.files).length : 0}`;
        }
        subDetail.innerText = details;
    } else if (subDetail) {
        subDetail.innerText = "";
    }
}

function renderTestCaseSelector(testPlan) {
    const tbody = document.getElementById("selectorTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    const cases = testPlan?.test_cases || [];
    if (cases.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #888;">Không tìm thấy kịch bản kiểm thử nào.</td></tr>';
        return;
    }
    
    cases.forEach(tc => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="text-align: center; padding: 6px 8px;">
                <input type="checkbox" class="tc-select-checkbox" data-id="${escapeHtml(tc.test_id)}" checked style="cursor: pointer; width: 14px; height: 14px;">
            </td>
            <td style="font-weight: bold;"><strong>${escapeHtml(tc.service)}</strong></td>
            <td><code style="font-family: 'JetBrains Mono', monospace; background: rgba(0,0,0,0.05); padding: 1px 4px;">${escapeHtml(tc.method)}</code></td>
            <td><span class="badge ${tc.type || ''}" style="font-size: 0.65rem; padding: 1px 4px; text-transform: uppercase;">${escapeHtml(tc.type)}</span></td>
            <td style="color: #666; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(tc.description)}">${escapeHtml(tc.description)}</td>
        `;
        tbody.appendChild(tr);
    });
    
    document.getElementById("selectAllCheckbox").checked = true;
}

function toggleSelectAllCheckbox(master) {
    const checkboxes = document.querySelectorAll(".tc-select-checkbox");
    checkboxes.forEach(cb => cb.checked = master.checked);
}

function toggleSelectAllTestCases(checked) {
    const master = document.getElementById("selectAllCheckbox");
    if (master) master.checked = checked;
    const checkboxes = document.querySelectorAll(".tc-select-checkbox");
    checkboxes.forEach(cb => cb.checked = checked);
}

async function submitTestCaseSelection() {
    if (!currentRunId) return;
    
    const checkboxes = document.querySelectorAll(".tc-select-checkbox");
    const selected_test_ids = [];
    checkboxes.forEach(cb => {
        if (cb.checked) {
            selected_test_ids.push(cb.getAttribute("data-id"));
        }
    });
    
    if (selected_test_ids.length === 0) {
        alert("Vui lòng chọn ít nhất một kịch bản kiểm thử để sinh code!");
        return;
    }
    
    // Disable resume button
    document.getElementById("btnResume").disabled = true;
    document.getElementById("btnResume").innerText = "Đang xử lý...";
    
    try {
        const response = await fetch(`/api/resume/${currentRunId}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ selected_test_ids: selected_test_ids })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Không thể tiếp tục sinh test.");
        }
        
        // Hide panel
        document.getElementById("selectionPanel").style.display = "none";
        
        appendTerminalLog(`> Đã gửi danh sách lựa chọn (${selected_test_ids.length} test case). Đang tiếp tục chạy Stage 3...`, "system-line");
        
        // Restart polling
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(pollStatus, 1000);
        
    } catch (error) {
        alert("Lỗi khi tiếp tục: " + error.message);
        document.getElementById("btnResume").disabled = false;
        document.getElementById("btnResume").innerText = "Tiếp tục sinh test 🚀";
    }
}

async function cancelRun() {
    if (confirm("Bạn có chắc chắn muốn hủy bỏ tiến trình này không?")) {
        document.getElementById("selectionPanel").style.display = "none";
        document.getElementById("progressContainer").style.display = "none";
        setButtonsRunningState(false);
        updateStatusBadge("Cancelled", "failed");
        appendTerminalLog("> Người dùng đã hủy bỏ tiến trình.", "error-line");
        document.getElementById("displayMental").innerText = "CANCELLED";
        currentRunId = null;
        if (pollInterval) clearInterval(pollInterval);
    }
}
