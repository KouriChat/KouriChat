// 配置页面主要逻辑
console.log('config-main.js 开始加载');

// 页面初始化
function initializeConfigPage() {
    console.log('初始化配置页面');
    
    // 初始化所有开关滑块
    if (typeof initializeSwitches === 'function') {
        initializeSwitches();
    }

    // 获取最新的配置数据
    fetch('/get_all_configs')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log("成功获取配置数据");
                
                // 更新所有配置项
                if (typeof updateAllConfigs === 'function') {
                    updateAllConfigs(data.configs);
                }

                // 更新任务列表
                const tasksInput = document.getElementById('TASKS');
                if (tasksInput && data.tasks) {
                    tasksInput.value = JSON.stringify(data.tasks);
                    if (typeof updateTaskList === 'function') {
                        updateTaskList();
                    }
                }

                // 重新初始化开关滑块
                if (typeof initializeSwitches === 'function') {
                    initializeSwitches();
                }
                
            } else {
                console.error('获取配置数据失败:', data.message);
                fallbackToLocalConfig();
            }
        })
        .catch(error => {
            console.error('获取配置数据请求失败:', error);
            fallbackToLocalConfig();
        });

    // 初始化背景
    fetch('/get_background')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success' && data.path) {
                document.body.style.backgroundImage = `url('${data.path}')`;
            }
        })
        .catch(error => console.error('Error:', error));
}

// 回退到本地配置
function fallbackToLocalConfig() {
    console.log("使用页面初始配置数据");
    const tasksInput = document.getElementById('TASKS');
    if (tasksInput && typeof updateTaskList === 'function') {
        updateTaskList();
    }
}

// 初始化工具提示
function initializeTooltips() {
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// 全局模型选择更新函数
window.updateModelSelect = function(providerId) {
    console.log('全局 updateModelSelect 被调用，参数:', providerId);
    
    const modelSelect = document.getElementById('model_select');
    const modelInput = document.getElementById('MODEL');
    const customModelInput = document.getElementById('customModelInput');
    
    if (!modelSelect) {
        console.error("模型选择器未找到!");
        return;
    }
    
    // 保存当前模型值，确保后续操作不会丢失
    const currentModelValue = modelInput ? modelInput.value : '';
    console.log("当前模型值:", currentModelValue);
    
    // 根据提供商重置选择框内容
    modelSelect.innerHTML = '';
    
    // 使用模型配置管理器获取模型选项
    if (typeof window.fetchModelConfigs === 'function') {
        window.fetchModelConfigs().then(configs => {
            if (configs && configs.models && configs.models[providerId]) {
                console.log(`为提供商 ${providerId} 加载 ${configs.models[providerId].length} 个模型`);
                configs.models[providerId].forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.id;
                    option.textContent = model.name || model.id;
                    modelSelect.appendChild(option);
                });
            } else {
                // 使用默认模型选项作为回退
                addDefaultModelOptions(providerId, modelSelect);
            }
            
            // 添加自定义选项
            modelSelect.innerHTML += '<option value="custom">自定义模型</option>';
            
            // 恢复选择状态
            restoreModelSelection(modelSelect, modelInput, customModelInput, currentModelValue, providerId);
        }).catch(error => {
            console.error('获取模型配置失败:', error);
            // 使用默认模型选项作为回退
            addDefaultModelOptions(providerId, modelSelect);
            modelSelect.innerHTML += '<option value="custom">自定义模型</option>';
            restoreModelSelection(modelSelect, modelInput, customModelInput, currentModelValue, providerId);
        });
    } else {
        // 如果没有配置管理器，使用默认选项
        addDefaultModelOptions(providerId, modelSelect);
        modelSelect.innerHTML += '<option value="custom">自定义模型</option>';
        restoreModelSelection(modelSelect, modelInput, customModelInput, currentModelValue, providerId);
    }
};

// 添加默认模型选项
function addDefaultModelOptions(providerId, modelSelect) {
    if (providerId === 'kourichat-global') {
        console.log("设置KouriChat模型选项");
        modelSelect.innerHTML = `
            <option value="kourichat-v3">kourichat-v3</option>
            <option value="gemini-2.5-pro">gemini-2.5-pro</option>
            <option value="gemini-2.5-flash">gemini-2.5-flash</option>
            <option value="gpt-4o">gpt-4o</option>
            <option value="grok-3">grok-3</option>
        `;
    } else if (providerId === 'siliconflow') {
        console.log("设置硅基流动模型选项");
        modelSelect.innerHTML = `
            <option value="deepseek-ai/DeepSeek-V3">deepseek-ai/DeepSeek-V3</option>
            <option value="deepseek-ai/DeepSeek-R1">deepseek-ai/DeepSeek-R1</option>
        `;
    } else if (providerId === 'deepseek') {
        console.log("设置DeepSeek模型选项");
        modelSelect.innerHTML = `
            <option value="deepseek-chat">deepseek-chat</option>
            <option value="deepseek-reasoner">deepseek-reasoner</option>
        `;
    }
}

// 恢复模型选择状态
function restoreModelSelection(modelSelect, modelInput, customModelInput, currentModelValue, providerId) {
    const availableOptions = Array.from(modelSelect.options).map(opt => opt.value);
    console.log("可用模型选项:", availableOptions);
    
    // 处理不同情况
    if (providerId === 'ollama' || providerId === 'custom') {
        // 1. 如果是自定义或Ollama提供商
        console.log("处理自定义/Ollama提供商");
        modelSelect.value = 'custom';
        
        if (customModelInput) {
            customModelInput.style.display = 'block';
            const inputField = customModelInput.querySelector('input');
            
            // 保留已有的值
            if (inputField && currentModelValue) {
                inputField.value = currentModelValue;
                // 确保隐藏字段也有值
                if (modelInput && !modelInput.value) {
                    modelInput.value = currentModelValue;
                }
            }
        }
    } else if (currentModelValue) {
        // 2. 有现有值的情况
        console.log("检查当前值是否在选项中:", currentModelValue);
        
        // 检查当前值是否在选项列表中
        const valueInOptions = availableOptions.includes(currentModelValue);
        
        if (valueInOptions) {
            // 2.1 当前值在选项中
            console.log("当前值在选项中，选择:", currentModelValue);
            modelSelect.value = currentModelValue;
            
            // 确保自定义输入框隐藏
            if (customModelInput) {
                customModelInput.style.display = 'none';
            }
        } else {
            // 2.2 当前值不在选项中，视为自定义模型
            console.log("当前值不在选项中，设为自定义模型:", currentModelValue);
            modelSelect.value = 'custom';
            
            // 显示并填充自定义输入框
            if (customModelInput) {
                customModelInput.style.display = 'block';
                const inputField = customModelInput.querySelector('input');
                if (inputField) {
                    inputField.value = currentModelValue;
                }
            }
        }
    } else {
        // 3. 无现有值，选择第一个选项
        console.log("无现有值，选择第一个选项");
        if (modelSelect.options.length > 0) {
            modelSelect.selectedIndex = 0;
            
            // 更新隐藏字段的值
            if (modelInput && modelSelect.value !== 'custom') {
                modelInput.value = modelSelect.value;
            }
            
            // 隐藏自定义输入框
            if (customModelInput && modelSelect.value !== 'custom') {
                customModelInput.style.display = 'none';
            }
        }
    }
    
    // 确保隐藏的MODEL字段有值
    if (modelInput && !modelInput.value && modelSelect.value !== 'custom') {
        modelInput.value = modelSelect.value;
    }
    
    // 如果选择了自定义模型但没有输入值，确保输入框可见
    if (modelSelect.value === 'custom' && customModelInput) {
        customModelInput.style.display = 'block';
    }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('配置页面DOM加载完成，开始初始化');
    
    // 初始化工具提示
    initializeTooltips();
    
    // 初始化配置页面
    initializeConfigPage();
    
    // 初始化所有温度滑块
    const temperatureSliders = document.querySelectorAll('[id$="_slider"].temperature-slider');
    temperatureSliders.forEach(slider => {
        const key = slider.id.replace('_slider', '');
        if (typeof updateTemperature === 'function') {
            updateTemperature(key, slider.value);
        }
    });
    
    // 添加保存按钮事件监听器
    const saveButton = document.getElementById('saveButton');
    if (saveButton) {
        saveButton.addEventListener('click', function() {
            console.log('保存按钮被点击');
            if (typeof saveConfig === 'function') {
                saveConfig();
            } else {
                console.error('saveConfig函数未定义');
            }
        });
    }
    
    // 添加导出按钮事件监听器
    const exportButton = document.getElementById('exportConfigBtn');
    if (exportButton) {
        exportButton.addEventListener('click', function() {
            console.log('导出按钮被点击');
            if (typeof exportConfig === 'function') {
                exportConfig();
            } else {
                console.error('exportConfig函数未定义');
            }
        });
    }
    
    // 添加导入按钮事件监听器
    const importButton = document.getElementById('importConfigBtn');
    if (importButton) {
        importButton.addEventListener('click', function() {
            console.log('导入按钮被点击');
            if (typeof importConfig === 'function') {
                importConfig();
            } else {
                console.error('importConfig函数未定义');
            }
        });
    }
});

console.log('config-main.js 加载完成');