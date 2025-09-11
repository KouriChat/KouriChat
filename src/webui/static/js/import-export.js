// 配置导入导出功能
console.log('配置导入导出模块加载');

// 导出配置
function exportConfig() {
    console.log('开始导出配置');
    
    // 收集所有配置数据
    const mainForm = document.getElementById('configForm');
    const otherForm = document.getElementById('otherConfigForm');
    const config = {};

    // 获取所有表单数据
    if (mainForm) {
        const formData = new FormData(mainForm);
        for (let [key, value] of formData.entries()) {
            if (typeof processFormValue === 'function') {
                processFormValue(config, key, value);
            } else {
                config[key] = value;
            }
        }
    }

    if (otherForm) {
        const otherFormData = new FormData(otherForm);
        for (let [key, value] of otherFormData.entries()) {
            if (typeof processFormValue === 'function') {
                processFormValue(config, key, value);
            } else {
                config[key] = value;
            }
        }
    }

    // 特别处理任务数据
    const tasksInput = document.getElementById('TASKS');
    if (tasksInput) {
        try {
            const tasksValue = tasksInput.value;
            if (tasksValue) {
                config['TASKS'] = JSON.parse(tasksValue);
            }
        } catch (e) {
            config['TASKS'] = [];
        }
    }

    // 特别处理群聊配置数据
    const groupChatInput = document.getElementById('GROUP_CHAT_CONFIG');
    if (groupChatInput) {
        try {
            const groupChatValue = groupChatInput.value;
            if (groupChatValue) {
                config['GROUP_CHAT_CONFIG'] = JSON.parse(groupChatValue);
            } else {
                config['GROUP_CHAT_CONFIG'] = [];
            }
        } catch (e) {
            console.error('解析群聊配置数据失败:', e);
            config['GROUP_CHAT_CONFIG'] = [];
        }
    }

    // 创建JSON文件并下载
    const dataStr = JSON.stringify(config, null, 2);
    const dataBlob = new Blob([dataStr], {type: 'application/json'});

    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10);
    const filename = `KouriChat_配置_${dateStr}.json`;

    const downloadLink = document.createElement('a');
    downloadLink.href = URL.createObjectURL(dataBlob);
    downloadLink.download = filename;

    // 模拟点击下载
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);

    // 显示成功通知
    if (typeof showSaveNotification === 'function') {
        showSaveNotification('配置已成功导出', 'success');
    } else {
        alert('配置已成功导出');
    }
}

// 导入配置
function importConfig() {
    console.log('开始导入配置');
    
    // 创建文件输入元素
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'application/json';
    fileInput.style.display = 'none';

    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length === 0) return;

        const file = e.target.files[0];
        const reader = new FileReader();

        reader.onload = function(event) {
            try {
                const config = JSON.parse(event.target.result);

                // 填充表单数据
                for (const [key, value] of Object.entries(config)) {
                    if (key === 'TASKS') {
                        // 特殊处理任务数据
                        const tasksInput = document.getElementById('TASKS');
                        if (tasksInput) {
                            tasksInput.value = JSON.stringify(value);
                        }
                        continue;
                    }

                    if (key === 'GROUP_CHAT_CONFIG') {
                        // 特殊处理群聊配置数据
                        const groupChatInput = document.getElementById('GROUP_CHAT_CONFIG');
                        if (groupChatInput) {
                            groupChatInput.value = JSON.stringify(value);
                            // 更新群聊配置界面
                            if (typeof window.groupChatConfigs !== 'undefined') {
                                window.groupChatConfigs = Array.isArray(value) ? value : [];
                                if (typeof renderGroupChatConfigList === 'function') {
                                    renderGroupChatConfigList();
                                }
                            }
                        }
                        continue;
                    }

                    // 处理普通输入字段
                    const input = document.querySelector(`[name="${key}"]`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = Boolean(value);
                            // 更新开关标签
                            if (typeof updateSwitchLabel === 'function') {
                                updateSwitchLabel(input);
                            }
                        } else {
                            input.value = value;
                        }

                        // 特别处理滑块
                        if (key === 'TEMPERATURE' || key === 'VISION_TEMPERATURE') {
                            const slider = document.getElementById(`${key}_slider`);
                            if (slider) {
                                slider.value = value;
                                // 使用统一的updateTemperature函数更新显示
                                if (typeof updateTemperature === 'function') {
                                    updateTemperature(key, value);
                                }
                            }
                        }
                    }

                    // 特殊处理用户列表
                    if (key === 'LISTEN_LIST') {
                        const userListElement = document.getElementById(`selected_users_${key}`);
                        const targetElement = document.getElementById(key);
                        
                        if (userListElement && targetElement) {
                            // 清空现有列表
                            userListElement.innerHTML = '';
                            
                            let userList = [];
                            if (Array.isArray(value)) {
                                userList = value;
                            } else if (typeof value === 'string') {
                                userList = value.split(',').map(item => item.trim()).filter(item => item);
                            }
                            
                            // 重新添加用户
                            userList.forEach(user => {
                                if (user) {
                                    const userDiv = document.createElement('div');
                                    userDiv.className = 'list-group-item d-flex justify-content-between align-items-center';
                                    userDiv.innerHTML = `
                                        ${user}
                                        <button type="button" class="btn btn-danger btn-sm" onclick="removeUser('${key}', '${user}')">
                                            <i class="bi bi-x-lg"></i>
                                        </button>
                                    `;
                                    userListElement.appendChild(userDiv);
                                }
                            });
                            
                            // 更新隐藏字段
                            targetElement.value = userList.join(',');
                        }
                    }
                }

                if (typeof showSaveNotification === 'function') {
                    showSaveNotification('配置已成功导入', 'success');
                } else {
                    alert('配置已成功导入');
                }
            } catch (error) {
                console.error('导入配置失败:', error);
                if (typeof showSaveNotification === 'function') {
                    showSaveNotification('导入配置失败: ' + error.message, 'error');
                } else {
                    alert('导入配置失败: ' + error.message);
                }
            }
        };

        reader.readAsText(file);
    });

    document.body.appendChild(fileInput);
    fileInput.click();
    document.body.removeChild(fileInput);
}

// 暴露全局函数
window.exportConfig = exportConfig;
window.importConfig = importConfig;

console.log('配置导入导出模块加载完成');