/**
 * 定时任务管理功能
 */

// 全局变量，存储当前任务列表
let scheduledTasks = [];

/**
 * 初始化定时任务功能
 */
function initScheduleTasks() {
  // 从隐藏字段加载任务数据
  loadTasksFromInput();

  // 更新任务列表UI
  updateTaskListUI();

  // 更新发送对象下拉框
  updateTaskChatIdOptions();

  // 添加事件监听器
  setupTaskEventListeners();
}

/**
 * 从隐藏输入字段加载任务数据
 */
function loadTasksFromInput() {
  const tasksInput = document.getElementById("TASKS");
  if (tasksInput && tasksInput.value) {
    try {
      scheduledTasks = JSON.parse(tasksInput.value);
    } catch (e) {
      console.error("解析任务数据失败:", e);
      scheduledTasks = [];
    }
  } else {
    scheduledTasks = [];
  }
}

/**
 * 更新任务列表UI
 */
function updateTaskListUI() {
  const container = document.getElementById("taskListContainer");
  if (!container) return;

  if (scheduledTasks.length === 0) {
    // 显示无任务提示
    container.innerHTML = `
            <div class="text-center text-muted p-4">
                <i class="bi bi-inbox fs-2"></i>
                <p class="mt-2">暂无定时任务</p>
            </div>
        `;
    return;
  }

  // 清空现有内容
  container.innerHTML = "";

  // 添加每个任务
  scheduledTasks.forEach((task) => {
    const taskItem = document.createElement("div");
    taskItem.className = "list-group-item";

    let scheduleInfo = "";
    if (task.schedule_type === "cron") {
      scheduleInfo = formatCronExpression(task.schedule_time);
    } else {
      scheduleInfo = formatInterval(task.schedule_time || task.interval);
    }

    taskItem.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="me-auto">
                    <div class="d-flex align-items-center mb-1">
                        <span class="badge bg-primary me-2">${
                          task.task_id
                        }</span>
                        <span class="badge ${
                          task.is_active ? "bg-success" : "bg-secondary"
                        } me-2">
                            ${task.is_active ? "运行中" : "已暂停"}
                        </span>
                    </div>
                    <div class="mb-1">
                        <i class="bi bi-person me-1"></i>发送给：${task.chat_id}
                    </div>
                    <div class="mb-1">
                        <i class="bi bi-clock me-1"></i>执行时间：${scheduleInfo}
                    </div>
                    <div class="text-muted small">
                        <i class="bi bi-chat-text me-1"></i>${task.content}
                    </div>
                </div>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick="editTask('${
                      task.task_id
                    }')" title="编辑任务">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-${
                      task.is_active ? "warning" : "success"
                    }" 
                            onclick="toggleTaskStatus('${task.task_id}')" 
                            title="${task.is_active ? "暂停任务" : "启动任务"}">
                        <i class="bi bi-${
                          task.is_active ? "pause" : "play"
                        }-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="showDeleteTaskModal('${
                      task.task_id
                    }')" title="删除任务">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;

    container.appendChild(taskItem);
  });
}

/**
 * 更新发送对象下拉框
 */
function updateTaskChatIdOptions() {
  const chatSelect = document.getElementById("taskChatId");
  if (!chatSelect) return;

  // 保存当前选中的值
  const currentValue = chatSelect.value;

  // 清空现有选项
  chatSelect.innerHTML = '<option value="">请选择发送对象</option>';

  // 从监听列表获取用户
  const userElements = document.querySelectorAll(
    "#selected_users_LISTEN_LIST .list-group-item"
  );
  userElements.forEach((element) => {
    const userName = element.textContent.trim().replace("×", "").trim();
    if (userName) {
      chatSelect.innerHTML += `<option value="${userName}">${userName}</option>`;
    }
  });

  // 恢复之前选中的值
  if (currentValue) {
    chatSelect.value = currentValue;
  }
}

/**
 * 设置任务相关的事件监听器
 */
function setupTaskEventListeners() {
  // 添加任务模态框显示事件
  const addTaskModal = document.getElementById("addTaskModal");
  if (addTaskModal) {
    addTaskModal.addEventListener("show.bs.modal", function () {
      // 重置表单
      document.getElementById("taskForm").reset();

      // 更新发送对象下拉框
      updateTaskChatIdOptions();

      // 默认显示cron输入框
      toggleScheduleInput();

      // 重置任务ID只读状态
      document.getElementById("taskId").readOnly = false;

      // 更新模态框标题
      document.getElementById("addTaskModalLabel").innerHTML =
        '<i class="bi bi-plus-circle me-2"></i>添加定时任务';

      // 更新保存按钮文本
      const saveButton = document.querySelector(
        "#addTaskModal .modal-footer .btn-primary"
      );
      saveButton.textContent = "保存";
    });
  }

  // 添加调度类型切换事件
  const scheduleType = document.getElementById("scheduleType");
  if (scheduleType) {
    scheduleType.addEventListener("change", toggleScheduleInput);
  }

  // 添加Cron表达式相关输入事件
  const cronInputs = [
    "cronHour",
    "cronMinute",
    "cronWeekday1",
    "cronWeekday2",
    "cronWeekday3",
    "cronWeekday4",
    "cronWeekday5",
    "cronWeekday6",
    "cronWeekday7",
  ];

  cronInputs.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.addEventListener("change", updateSchedulePreview);
    }
  });

  // 添加间隔时间相关输入事件
  const intervalInputs = ["intervalValue", "intervalUnit"];
  intervalInputs.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.addEventListener("change", updateSchedulePreview);
      element.addEventListener("input", updateSchedulePreview);
    }
  });

  // 添加删除任务确认按钮事件
  const confirmDeleteBtn = document.getElementById("confirmDeleteTaskBtn");
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", function () {
      const taskId = document.getElementById("deleteTaskId").textContent;
      deleteTask(taskId);

      // 隐藏模态框
      const modal = bootstrap.Modal.getInstance(
        document.getElementById("deleteTaskModal")
      );
      modal.hide();
    });
  }
}

/**
 * 切换调度类型输入框
 */
function toggleScheduleInput() {
  const scheduleType = document.getElementById("scheduleType").value;
  const cronInput = document.getElementById("cronInputGroup");
  const intervalInput = document.getElementById("intervalInputGroup");

  if (scheduleType === "cron") {
    cronInput.style.display = "block";
    intervalInput.style.display = "none";
  } else {
    cronInput.style.display = "none";
    intervalInput.style.display = "block";
  }

  updateSchedulePreview();
}

/**
 * 更新调度时间预览
 */
function updateSchedulePreview() {
  const scheduleType = document.getElementById("scheduleType").value;
  const preview = document.getElementById("schedulePreview");

  if (scheduleType === "cron") {
    const hour = document.getElementById("cronHour").value;
    const minute = document.getElementById("cronMinute").value;
    const weekdays = [];
    const displayWeekdays = [];

    // 获取选中的星期
    for (let i = 1; i <= 7; i++) {
      if (document.getElementById(`cronWeekday${i}`).checked) {
        // cron表达式：1=周一, 2=周二, ..., 7=周日, 0=周日
        // 界面显示：1=一, 2=二, ..., 7=日
        weekdays.push(i === 7 ? 0 : i); // cron格式：周日为0，其他为1-6
        displayWeekdays.push(["一", "二", "三", "四", "五", "六", "日"][i - 1]); // 显示格式：直接对应
      }
    }

    if (weekdays.length === 0) {
      preview.textContent = "请选择执行周期";
      return;
    }

    let previewText = `每天 ${
      hour === "*" ? "每小时" : hour + "点"
    } ${minute}分`;
    if (weekdays.length < 7) {
      previewText = `每周 ${displayWeekdays.join("、")} ${
        hour === "*" ? "每小时" : hour + "点"
      } ${minute}分`;
    }

    preview.textContent = previewText;

    // 更新cron表达式 - 修改为5字段格式
    const cronExp = `${minute} ${hour} * * ${weekdays.join(",")}`;
    document.getElementById("cronExpression").value = cronExp;
  } else {
    const value = document.getElementById("intervalValue").value;
    const unit = document.getElementById("intervalUnit").value;

    if (!value) {
      preview.textContent = "请设置间隔时间";
      return;
    }

    let unitText = "";
    switch (unit) {
      case "60":
        unitText = "分钟";
        break;
      case "3600":
        unitText = "小时";
        break;
      case "86400":
        unitText = "天";
        break;
    }

    preview.textContent = `每 ${value} ${unitText}`;
  }
}

/**
 * 设置时间间隔
 * @param {number} value - 间隔值
 * @param {string} unit - 间隔单位
 */
function setInterval(value, unit) {
  document.getElementById("intervalValue").value = value;
  document.getElementById("intervalUnit").value = unit;
  updateSchedulePreview();
}

/**
 * 保存任务
 */
function saveTask() {
  // 获取表单数据
  const taskId = document.getElementById("taskId").value.trim();
  const chatId = document.getElementById("taskChatId").value;
  const content = document.getElementById("taskContent").value.trim();
  const scheduleType = document.getElementById("scheduleType").value;

  // 验证必填字段
  if (!taskId || !chatId || !content) {
    showToast("请填写所有必填字段", "error");
    return;
  }

  const task = {
    task_id: taskId,
    chat_id: chatId,
    content: content,
    schedule_type: scheduleType,
    is_active: true,
  };

  // 根据调度类型设置相应的值
  if (scheduleType === "cron") {
    const cronExp = document.getElementById("cronExpression").value;
    if (!cronExp) {
      showToast("请设置执行时间", "error");
      return;
    }
    task.schedule_time = cronExp;
  } else {
    const value = document.getElementById("intervalValue").value;
    const unit = document.getElementById("intervalUnit").value;

    if (!value) {
      showToast("请设置间隔时间", "error");
      return;
    }

    // 计算总秒数
    const totalSeconds = parseInt(value) * parseInt(unit);
    task.schedule_time = totalSeconds.toString();
    task.interval = totalSeconds.toString();
  }

  // 检查任务ID是否已存在
  const existingIndex = scheduledTasks.findIndex((t) => t.task_id === taskId);
  if (existingIndex >= 0) {
    // 更新现有任务
    scheduledTasks[existingIndex] = task;
  } else {
    // 添加新任务
    scheduledTasks.push(task);
  }

  // 更新隐藏输入框的值
  document.getElementById("TASKS").value = JSON.stringify(scheduledTasks);

  // 更新任务列表UI
  updateTaskListUI();

  // 关闭模态框
  const modal = bootstrap.Modal.getInstance(
    document.getElementById("addTaskModal")
  );
  modal.hide();

  // 显示成功提示
  showToast('任务已保存，请点击底部的"保存所有设置"按钮保存更改', "success");
}

/**
 * 编辑任务
 * @param {string} taskId - 任务ID
 */
function editTask(taskId) {
  // 查找指定任务
  const task = scheduledTasks.find((t) => t.task_id === taskId);
  if (!task) {
    showToast("未找到指定任务", "error");
    return;
  }

  // 填充表单
  document.getElementById("taskId").value = task.task_id;
  document.getElementById("taskId").readOnly = true; // 编辑模式下不允许修改ID
  document.getElementById("taskChatId").value = task.chat_id;
  document.getElementById("taskContent").value = task.content;
  document.getElementById("scheduleType").value = task.schedule_type;

  // 根据任务类型设置调度时间
  toggleScheduleInput(); // 先切换显示正确的输入框

  if (task.schedule_type === "cron") {
    // 解析cron表达式
    const cronParts = task.schedule_time.split(" ");
    if (cronParts.length >= 5) {
      document.getElementById("cronMinute").value = cronParts[0];
      document.getElementById("cronHour").value = cronParts[1];

      // 设置星期几
      const weekdays = cronParts[4].split(",");
      for (let i = 1; i <= 7; i++) {
        const dayValue = i === 7 ? "0" : i.toString();
        document.getElementById(`cronWeekday${i}`).checked =
          weekdays.includes(dayValue);
      }
    }

    document.getElementById("cronExpression").value = task.schedule_time;
  } else {
    // 解析间隔时间
    const intervalSeconds = parseInt(task.interval || task.schedule_time);

    if (intervalSeconds % 86400 === 0) {
      // 天
      document.getElementById("intervalValue").value = intervalSeconds / 86400;
      document.getElementById("intervalUnit").value = "86400";
    } else if (intervalSeconds % 3600 === 0) {
      // 小时
      document.getElementById("intervalValue").value = intervalSeconds / 3600;
      document.getElementById("intervalUnit").value = "3600";
    } else {
      // 分钟
      document.getElementById("intervalValue").value = intervalSeconds / 60;
      document.getElementById("intervalUnit").value = "60";
    }
  }

  // 更新预览
  updateSchedulePreview();

  // 显示模态框
  const modal = new bootstrap.Modal(document.getElementById("addTaskModal"));
  modal.show();

  // 更新模态框标题
  document.getElementById("addTaskModalLabel").innerHTML =
    '<i class="bi bi-pencil-square me-2"></i>编辑定时任务';

  // 更改保存按钮文本
  const saveButton = document.querySelector(
    "#addTaskModal .modal-footer .btn-primary"
  );
  saveButton.textContent = "保存修改";
}

/**
 * 显示删除任务确认模态框
 * @param {string} taskId - 任务ID
 */
function showDeleteTaskModal(taskId) {
  document.getElementById("deleteTaskId").textContent = taskId;
  const modal = new bootstrap.Modal(document.getElementById("deleteTaskModal"));
  modal.show();
}

/**
 * 删除任务
 * @param {string} taskId - 任务ID
 */
function deleteTask(taskId) {
  // 从任务列表中删除
  scheduledTasks = scheduledTasks.filter((task) => task.task_id !== taskId);

  // 更新隐藏输入框的值
  document.getElementById("TASKS").value = JSON.stringify(scheduledTasks);

  // 更新任务列表UI
  updateTaskListUI();

  // 显示成功提示
  showToast('任务已删除，请点击底部的"保存所有设置"按钮保存更改', "success");
}

/**
 * 切换任务状态（启用/禁用）
 * @param {string} taskId - 任务ID
 */
function toggleTaskStatus(taskId) {
  // 查找指定任务
  const taskIndex = scheduledTasks.findIndex((task) => task.task_id === taskId);
  if (taskIndex === -1) {
    showToast("未找到指定任务", "error");
    return;
  }

  // 切换状态
  scheduledTasks[taskIndex].is_active = !scheduledTasks[taskIndex].is_active;

  // 更新隐藏输入框的值
  document.getElementById("TASKS").value = JSON.stringify(scheduledTasks);

  // 更新任务列表UI
  updateTaskListUI();

  // 显示成功提示
  const status = scheduledTasks[taskIndex].is_active ? "启用" : "禁用";
  showToast(
    `任务已${status}，请点击底部的"保存所有设置"按钮保存更改`,
    "success"
  );
}

/**
 * 格式化Cron表达式为可读文本
 * @param {string} cronExp - Cron表达式
 * @returns {string} 格式化后的文本
 */
function formatCronExpression(cronExp) {
  const [minute, hour, day, month, weekday] = cronExp.split(" ");
  let result = "";

  // 处理星期
  if (weekday !== "*") {
    const weekdays = weekday.split(",").map((w) => {
      const val = parseInt(w);
      // cron格式：0=周日, 1=周一, 2=周二, ..., 6=周六
      if (val === 0) return "日";
      return ["", "一", "二", "三", "四", "五", "六"][val];
    });
    result += `每周${weekdays.join("、")} `;
  } else {
    result += "每天 ";
  }

  // 处理时间
  if (hour === "*") {
    result += `每小时${minute}分`;
  } else {
    result += `${hour}点${minute}分`;
  }

  return result;
}

/**
 * 格式化时间间隔为可读文本
 * @param {string|number} seconds - 间隔秒数
 * @returns {string} 格式化后的文本
 */
function formatInterval(seconds) {
  const intervalSeconds = parseInt(seconds);

  if (intervalSeconds % 86400 === 0) {
    // 天
    return `每${intervalSeconds / 86400}天`;
  } else if (intervalSeconds % 3600 === 0) {
    // 小时
    return `每${intervalSeconds / 3600}小时`;
  } else {
    // 分钟
    return `每${intervalSeconds / 60}分钟`;
  }
}

/**
 * 显示提示消息
 * @param {string} message - 消息内容
 * @param {string} type - 消息类型（success, error, warning, info）
 */
function showToast(message, type = "info") {
  // 检查是否存在全局showSaveNotification函数
  if (typeof showSaveNotification === "function") {
    showSaveNotification(message, type === "error" ? "danger" : type);
    return;
  }

  // 如果没有全局函数，使用alert作为备选
  if (type === "error") {
    alert("错误: " + message);
  } else {
    alert(message);
  }
}

/**
 * 删除任务
 * @param {string} taskId - 任务ID
 */
function deleteTask(taskId) {
  // 从任务列表中删除
  scheduledTasks = scheduledTasks.filter((task) => task.task_id !== taskId);

  // 更新隐藏输入框的值
  document.getElementById("TASKS").value = JSON.stringify(scheduledTasks);

  // 更新任务列表UI
  updateTaskListUI();

  // 显示成功提示
  showToast('任务已删除，请点击底部的"保存所有设置"按钮保存更改', "success");
}

/**
 * 删除任务确认模态框
 */
const deleteTaskModal = `
    <!-- 删除任务确认模态框 -->
    <div class="modal fade" id="deleteTaskModal" tabindex="-1" aria-labelledby="deleteTaskModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="deleteTaskModalLabel">
                        <i class="bi bi-exclamation-triangle text-warning me-2"></i>确认删除
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <p>确定要删除任务 "<span id="deleteTaskId" class="fw-bold text-primary"></span>" 吗？</p>
                    <p class="text-muted small">此操作不可撤销。</p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-danger" id="confirmDeleteTaskBtn">
                        <i class="bi bi-trash me-1"></i>确认删除
                    </button>
                </div>
            </div>
        </div>
    </div>
`;

/**
 * 初始化删除任务模态框
 */
function initDeleteTaskModal() {
  // 检查是否已存在删除模态框
  if (!document.getElementById("deleteTaskModal")) {
    // 将模态框HTML添加到页面
    document.body.insertAdjacentHTML("beforeend", deleteTaskModal);
  }
}

/**
 * 监听用户列表变化，更新任务发送对象选项
 */
function observeUserListChanges() {
  const userListContainer = document.getElementById(
    "selected_users_LISTEN_LIST"
  );
  if (!userListContainer) return;

  // 使用MutationObserver监听用户列表变化
  const observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      if (mutation.type === "childList") {
        // 用户列表发生变化时，更新任务的发送对象选项
        updateTaskChatIdOptions();
      }
    });
  });

  // 开始观察
  observer.observe(userListContainer, {
    childList: true,
    subtree: true,
  });
}

/**
 * 页面卸载前的清理工作
 */
function cleanup() {
  // 清理事件监听器等
  console.log("定时任务模块清理完成");
}

// 页面加载完成后初始化
document.addEventListener("DOMContentLoaded", function () {
  // 延迟初始化，确保DOM已完全加载
  setTimeout(() => {
    initScheduleTasks();
    initDeleteTaskModal();
    observeUserListChanges();
  }, 500);
});

// 页面卸载时清理
window.addEventListener("beforeunload", cleanup);
