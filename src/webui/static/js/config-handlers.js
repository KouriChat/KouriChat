// 配置处理函数
console.log('配置处理函数模块加载');

// 初始化所有开关滑块
function initializeSwitches() {
    console.log('初始化开关滑块');
    const switches = document.querySelectorAll('input[type="checkbox"][role="switch"]');
    switches.forEach(switchElem => {
        const label = document.getElementById(switchElem.id + '_label');
        if (label) {
            label.textContent = switchElem.checked ? '启用' : '停用';
            console.log(`初始化开关 ${switchElem.id}: ${switchElem.checked ? '启用' : '停用'}`);
        }
    });
}

// 显示保存通知
function showSaveNotification(message, type = 'success') {
    console.log('显示保存通知:', message, type);
    const notification = document.getElementById('saveNotification');
    const messageElement = document.getElementById('saveNotificationMessage');

    if (!notification || !messageElement) {
        console.error('通知元素未找到');
        // 使用alert作为后备
        alert(message);
        return;
    }

    // 移除现有的背景色类
    notification.classList.remove('bg-success', 'bg-danger');

    // 根据类型设置样式
    if (type === 'success') {
        notification.classList.add('bg-success');
    } else {
        notification.classList.add('bg-danger');
    }

    messageElement.textContent = message;

    const toast = new bootstrap.Toast(notification, {
        animation: true,
        autohide: true,
        delay: 3000
    });
    toast.show();
}

// 全局统一updateTemperature函数 - 处理所有温度滑块
function updateTemperature(key, value) {
    console.log('更新温度值:', key, value);
    // 将字符串转换为数字并保留一位小数
    const numValue = parseFloat(value).toFixed(1);

    // 更新显示值
    const displayElement = document.getElementById(key + '_display');
    if (displayElement) {
        displayElement.classList.add('updating');
        displayElement.textContent = numValue;
        setTimeout(() => {
            displayElement.classList.remove('updating');
        }, 300);
    }

    // 更新隐藏的实际提交值
    const inputElement = document.getElementById(key);
    if (inputElement) {
        inputElement.value = numValue;
        // 触发 change 事件以确保表单能捕获到值的变化
        const event = new Event('change', { bubbles: true });
        inputElement.dispatchEvent(event);
    }

    // 更新滑块位置（如果不是从滑块触发的事件）
    const sliderElement = document.getElementById(key + '_slider');
    if (sliderElement && sliderElement.value !== numValue) {
        sliderElement.value = numValue;
    }

    // 视觉反馈
    const container = inputElement?.closest('.mb-3') || displayElement?.closest('.mb-3');
    if (container) {
        container.style.transition = 'background-color 0.3s';
        container.style.backgroundColor = 'rgba(var(--bs-primary-rgb), 0.1)';
        setTimeout(() => {
            container.style.backgroundColor = '';
        }, 300);
    }
}

// 更新数值滑块的值
function updateRangeValue(key, value) {
    console.log('更新范围值:', key, value);
    const display = document.getElementById(`${key}_display`);
    const input = document.getElementById(key);
    if (display) {
        display.textContent = value;
    }
    if (input) {
        input.value = value;
    }
}

// 更新开关标签
function updateSwitchLabel(checkbox) {
    const label = document.getElementById(checkbox.id + '_label');
    if (label) {
        label.textContent = checkbox.checked ? '启用' : '停用';
    }
    console.log(`${checkbox.id} 状态已更新为: ${checkbox.checked}`);
}

// 添加新用户到监听列表
function addNewUser(key) {
    console.log('添加新用户到:', key);
    const inputElement = document.getElementById('input_' + key);
    const newValue = inputElement.value.trim();

    if (newValue) {
        const targetElement = document.getElementById(key);
        const currentValues = targetElement.value ? targetElement.value.split(',') : [];
        if (!currentValues.includes(newValue)) {
            currentValues.push(newValue);
            targetElement.value = currentValues.join(',');

            // 添加到用户列表显示
            const userListElement = document.getElementById('selected_users_' + key);
            const userDiv = document.createElement('div');
            userDiv.className = 'list-group-item d-flex justify-content-between align-items-center';
            userDiv.innerHTML = `
                ${newValue}
                <button type="button" class="btn btn-danger btn-sm" onclick="removeUser('${key}', '${newValue}')">
                    <i class="bi bi-x-lg"></i>
                </button>
            `;
            userListElement.appendChild(userDiv);

            // 清空输入框
            inputElement.value = '';
        }
    }
    
    // 更新相关组件
    if (typeof updateTaskChatIdOptions === 'function') {
        updateTaskChatIdOptions();
    }
    if (key === 'LISTEN_LIST' && typeof updateGroupChatConfigSelects === 'function') {
        updateGroupChatConfigSelects();
    }
}

// 从监听列表移除用户
function removeUser(key, userToRemove) {
    console.log('移除用户:', key, userToRemove);
    const targetElement = document.getElementById(key);
    const userListElement = document.getElementById('selected_users_' + key);

    // 更新隐藏的input值
    let currentValues = targetElement.value ? targetElement.value.split(',') : [];
    currentValues = currentValues.filter(user => user !== userToRemove);
    targetElement.value = currentValues.join(',');

    // 从显示列表中移除
    const userElements = userListElement.getElementsByClassName('list-group-item');
    for (let element of userElements) {
        if (element.textContent.trim().replace('×', '').trim() === userToRemove) {
            element.remove();
            break;
        }
    }
    
    // 更新相关组件
    if (typeof updateTaskChatIdOptions === 'function') {
        updateTaskChatIdOptions();
    }
    if (key === 'LISTEN_LIST' && typeof updateGroupChatConfigSelects === 'function') {
        updateGroupChatConfigSelects();
    }
}

// 处理表单值
function processFormValue(config, key, value) {
    console.log('处理表单值:', key, value);
    
    // 处理列表类型
    if (key === 'LISTEN_LIST') {
        config[key] = value;
    }
    // 处理数字类型
    else if (['TEMPERATURE', 'VISION_TEMPERATURE', 'MAX_TOKEN',
             'MIN_COUNTDOWN_HOURS', 'MAX_COUNTDOWN_HOURS', 'MAX_GROUPS', 'QUEUE_TIMEOUT'].includes(key)) {
        const numValue = parseFloat(value);
        if (!isNaN(numValue)) {
            config[key] = numValue;
            if (['MAX_TOKEN', 'MAX_GROUPS', 'QUEUE_TIMEOUT'].includes(key)) {
                config[key] = Math.round(numValue);
            }
        } else {
            config[key] = value;
        }
    }
    // 处理任务配置
    else if (key === 'TASKS') {
        try {
            config[key] = JSON.parse(value);
        } catch (e) {
            console.error("解析任务数据失败:", e);
            config[key] = [];
        }
    }
    // 处理群聊配置
    else if (key === 'GROUP_CHAT_CONFIG') {
        try {
            config[key] = JSON.parse(value);
        } catch (e) {
            console.error("解析群聊配置失败:", e);
            config[key] = [];
        }
    }
    // 处理布尔值
    else if (key === 'NETWORK_SEARCH_ENABLED' || key === 'WEBLENS_ENABLED') {
        const checkbox = document.getElementById(key);
        if (checkbox && checkbox.type === 'checkbox') {
            config[key] = checkbox.checked;
        } else {
            if (typeof value === 'string') {
                config[key] = value.toLowerCase() === 'true';
            } else {
                config[key] = Boolean(value);
            }
        }
    }
    else if (typeof value === 'string' && (value.toLowerCase() === 'true' || value.toLowerCase() === 'false')) {
        config[key] = value.toLowerCase() === 'true';
    }
    // 其他类型直接保存
    else {
        config[key] = value;
    }
}

// 更新所有配置项
function updateAllConfigs(configs) {
    console.log('更新所有配置项');
    
    // 遍历所有配置组和配置项
    for (const groupKey in configs) {
        const group = configs[groupKey];
        for (const configKey in group) {
            const config = group[configKey];
            const element = document.getElementById(configKey);
            if (element) {
                // 获取实际值
                let value;
                if (config !== null && typeof config === 'object') {
                    value = config.value !== undefined ? config.value : 
                           (config.default !== undefined ? config.default : null);
                } else {
                    value = config;
                }
                
                console.log(`设置配置项 ${configKey} = ${JSON.stringify(value)}`);
                
                // 根据元素类型设置值
                if (element.type === 'checkbox') {
                    let isChecked = false;
                    if (typeof value === 'boolean') {
                        isChecked = value;
                    } else if (typeof value === 'string') {
                        isChecked = value.toLowerCase() === 'true';
                    } else {
                        isChecked = Boolean(value);
                    }
                    element.checked = isChecked;
                    
                    // 如果是开关滑块，更新标签
                    const label = document.getElementById(element.id + '_label');
                    if (label) {
                        label.textContent = element.checked ? '启用' : '停用';
                        console.log(`更新开关 ${element.id}: ${element.checked ? '启用' : '停用'}`);
                    }
                } else if (element.tagName === 'SELECT') {
                    if (value !== null && value !== undefined) {
                        element.value = value;
                    }
                } else {
                    if (value !== null && value !== undefined) {
                        // 检查 value 是否为对象 (数组的 typeof 也是 'object')
                        if (typeof value === 'object') {
                            // 如果是对象，必须字符串化
                            element.value = JSON.stringify(value);
                        } else {
                            // 如果是原始类型 (string, number)，直接赋值
                            element.value = value;
                        }
                    }
                }

                // 特殊处理滑块
                const slider = document.getElementById(`${configKey}_slider`);
                if (slider) {
                    if (value !== null && value !== undefined) {
                        slider.value = value;
                        const display = document.getElementById(`${configKey}_display`);
                        if (display) {
                            display.textContent = typeof value === 'number' ?
                                (configKey === 'TEMPERATURE' ? value.toFixed(1) : value) :
                                value;
                        }
                    }
                }

                // 特殊处理用户列表
                if (configKey === 'LISTEN_LIST') {
                    let userList = [];
                    
                    if (Array.isArray(value)) {
                        userList = value;
                    } else if (typeof value === 'string') {
                        userList = value.split(',').map(item => item.trim()).filter(item => item);
                    } else if (value && typeof value === 'object' && value.value) {
                        if (Array.isArray(value.value)) {
                            userList = value.value;
                        } else if (typeof value.value === 'string') {
                            userList = value.value.split(',').map(item => item.trim()).filter(item => item);
                        }
                    }
                    
                    if (userList.length > 0) {
                        const userListElement = document.getElementById(`selected_users_${configKey}`);
                        if (userListElement) {
                            userListElement.innerHTML = '';
                            userList.forEach(user => {
                                if (user) {
                                    const userDiv = document.createElement('div');
                                    userDiv.className = 'list-group-item d-flex justify-content-between align-items-center';
                                    userDiv.innerHTML = `
                                        ${user}
                                        <button type="button" class="btn btn-danger btn-sm" onclick="removeUser('${configKey}', '${user}')">
                                            <i class="bi bi-x-lg"></i>
                                        </button>
                                    `;
                                    userListElement.appendChild(userDiv);
                                }
                            });
                            
                            if (element) {
                                element.value = userList.join(',');
                            }
                        }
                    }
                }
            }
        }
    }
}

// 保存配置
function saveConfig(config) {
    console.log('保存配置:', config);
    
    // 如果没有传入配置，收集表单数据
    if (!config) {
        config = {};
        const mainForm = document.getElementById('configForm');
        const otherForm = document.getElementById('otherConfigForm');
        
        if (mainForm) {
            const formData = new FormData(mainForm);
            for (let [key, value] of formData.entries()) {
                processFormValue(config, key, value);
            }
        }
        
        if (otherForm) {
            const otherFormData = new FormData(otherForm);
            for (let [key, value] of otherFormData.entries()) {
                processFormValue(config, key, value);
            }
        }
        
        // 特别处理复选框
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            const name = checkbox.name?.trim();
            if (name && !config.hasOwnProperty(name)) {
                config[name] = checkbox.checked;
            }
        });
    }
    
    // 数据格式检查
    for (const key in config) {
        if (key === 'LISTEN_LIST' && typeof config[key] === 'string') {
            config[key] = config[key].split(',')
                .map(item => item.trim())
                .filter(item => item);
        }
        else if (key === 'GROUP_CHAT_CONFIG') {
            if (typeof config[key] === 'string') {
                try {
                    config[key] = JSON.parse(config[key]);
                } catch (e) {
                    console.error('解析群聊配置失败:', e);
                    config[key] = [];
                }
            } else if (!Array.isArray(config[key])) {
                config[key] = [];
            }
        }
        else if (['MAX_TOKEN', 'TEMPERATURE', 'VISION_TEMPERATURE',
                  'MIN_COUNTDOWN_HOURS', 'MAX_COUNTDOWN_HOURS', 'MAX_GROUPS', 'QUEUE_TIMEOUT'].includes(key)) {
            const numValue = parseFloat(config[key]);
            if (!isNaN(numValue)) {
                config[key] = numValue;
                if (['MAX_TOKEN', 'MAX_GROUPS', 'QUEUE_TIMEOUT'].includes(key)) {
                    config[key] = Math.round(numValue);
                }
            }
        }
        else if (key === 'NETWORK_SEARCH_ENABLED' || key === 'WEBLENS_ENABLED') {
            const checkbox = document.getElementById(key);
            if (checkbox && checkbox.type === 'checkbox') {
                config[key] = checkbox.checked;
            } else {
                if (typeof config[key] === 'string') {
                    config[key] = config[key].toLowerCase() === 'true';
                } else {
                    config[key] = Boolean(config[key]);
                }
            }
        }
    }

    // 确保API相关配置被正确保存
    const baseUrlInput = document.getElementById('DEEPSEEK_BASE_URL');
    const modelInput = document.getElementById('MODEL');
    const apiKeyInput = document.getElementById('DEEPSEEK_API_KEY');

    if (baseUrlInput) config['DEEPSEEK_BASE_URL'] = baseUrlInput.value;
    if (modelInput) config['MODEL'] = modelInput.value;
    if (apiKeyInput) config['DEEPSEEK_API_KEY'] = apiKeyInput.value;

    // 确保图像识别API相关配置被正确保存
    const visionBaseUrlInput = document.getElementById('VISION_BASE_URL');
    const visionModelInput = document.getElementById('VISION_MODEL');
    const visionApiKeyInput = document.getElementById('VISION_API_KEY');
    
    if (visionBaseUrlInput) config['VISION_BASE_URL'] = visionBaseUrlInput.value;
    if (visionModelInput) config['VISION_MODEL'] = visionModelInput.value;
    if (visionApiKeyInput) config['VISION_API_KEY'] = visionApiKeyInput.value;

    console.log("发送配置数据:", config);

    // 发送保存请求
    fetch('/save', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        body: JSON.stringify(config)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            showSaveNotification(data.message);
            console.log('配置保存成功');
        } else {
            showSaveNotification(data.message, 'error');
        }
    })
    .catch(error => {
        console.error('保存配置失败:', error);
        showSaveNotification('保存配置失败: ' + error.message, 'error');
    });
}

// 暴露全局函数
window.initializeSwitches = initializeSwitches;
window.showSaveNotification = showSaveNotification;
window.updateTemperature = updateTemperature;
window.updateRangeValue = updateRangeValue;
window.updateSwitchLabel = updateSwitchLabel;
window.addNewUser = addNewUser;
window.removeUser = removeUser;
window.processFormValue = processFormValue;
window.updateAllConfigs = updateAllConfigs;
window.saveConfig = saveConfig;

console.log('配置处理函数模块加载完成');