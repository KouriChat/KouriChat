// 群聊配置相关功能
window.groupChatConfigs = [];
let groupChatConfigIndex = 0;

// 初始化群聊配置
window.initGroupChatConfig = function initGroupChatConfig() {
    const configInput = document.getElementById('GROUP_CHAT_CONFIG');
    if (configInput && configInput.value) {
        try {
            window.groupChatConfigs = JSON.parse(configInput.value);
        } catch (e) {
            console.error('解析群聊配置失败:', e);
            window.groupChatConfigs = [];
        }
    }
    renderGroupChatConfigList();
    updateAddGroupChatButton();
}

// 添加新的群聊配置
function addGroupChatConfig() {
    // 检查群聊配置数量限制
    if (window.groupChatConfigs.length >= 1) {
        alert('当前版本仅支持一个群聊配置，多个群聊会导致记忆混乱。\n\n支持私聊和群聊同步进行，但群聊配置限制为1个。');
        return;
    }
    
    const newConfig = {
        id: 'group_' + Date.now(),
        groupName: '',
        avatar: '',
        triggers: [],
        enableAtTrigger: true  // 默认启用@触发
    };
    window.groupChatConfigs.push(newConfig);
    updateGroupChatConfigData();
    renderGroupChatConfigList();
    updateAddGroupChatButton();
}

// 渲染群聊配置列表
window.renderGroupChatConfigList = function renderGroupChatConfigList() {
    const container = document.getElementById('groupChatConfigList');
    if (!container) return;
    
    if (window.groupChatConfigs.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted p-4 border rounded">
                <i class="bi bi-chat-dots fs-2"></i>
                <p class="mt-2 mb-0">暂无群聊配置</p>
                <small>点击上方"添加群聊配置"按钮开始设置</small>
                <small class="text-warning d-block mt-2">
                    <i class="bi bi-info-circle me-1"></i>
                    支持私聊和群聊同步进行，当前版本限制群聊配置为1个
                </small>
            </div>
        `;
        updateAddGroupChatButton();
        return;
    }
    
    container.innerHTML = window.groupChatConfigs.map((config, index) => `
        <div class="config-item mb-3 p-3 border rounded" data-config-id="${config.id}">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="mb-0">
                    <i class="bi bi-chat-square-text me-2"></i>
                    群聊配置 ${index + 1}
                </h6>
                <button type="button" class="btn btn-outline-danger btn-sm" 
                        onclick="removeGroupChatConfig('${config.id}')" title="删除此群聊配置">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
            
            <div class="row">
                <!-- 群聊名称 -->
                <div class="col-md-6 mb-3">
                    <label class="form-label">
                        <i class="bi bi-people me-1"></i>群聊名称
                        <span class="text-danger">*</span>
                    </label>
                    <select class="form-select" 
                            onchange="updateGroupChatConfigField('${config.id}', 'groupName', this.value)">
                        <option value="">请选择群聊名称</option>
                        ${getUserListOptions(config.groupName)}
                    </select>
                </div>
                
                <!-- 使用的人设 -->
                <div class="col-md-6 mb-3">
                    <label class="form-label">
                        <i class="bi bi-person-badge me-1"></i>使用的人设
                        <span class="text-danger">*</span>
                    </label>
                    <select class="form-select" 
                            onchange="updateGroupChatConfigField('${config.id}', 'avatar', this.value)">
                        <option value="">请选择人设</option>
                        ${getAvatarOptions(config.avatar)}
                    </select>
                </div>
            </div>
            
            <!-- @触发开关 -->
            <div class="mb-3">
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" 
                           id="atTrigger_${config.id}" 
                           ${config.enableAtTrigger !== false ? 'checked' : ''}
                           onchange="updateGroupChatConfigField('${config.id}', 'enableAtTrigger', this.checked)">
                    <label class="form-check-label" for="atTrigger_${config.id}">
                        <i class="bi bi-at me-1"></i>启用@机器人名字触发
                    </label>
                </div>
                <div class="form-text">
                    <i class="bi bi-info-circle me-1"></i>
                    开启后，@机器人名字也会触发回复（建议保持开启）
                </div>
            </div>

            <!-- 触发词配置 -->
            <div class="mb-3">
                <label class="form-label">
                    <i class="bi bi-chat-left-quote me-1"></i>触发词设置
                    <span class="text-danger">*</span>
                </label>
                <div class="form-text mb-2">
                    <i class="bi bi-info-circle me-1"></i>
                    群聊中包含这些词语时会触发回复（如：角色名、小名、昵称等）
                </div>
                
                <div class="input-group mb-2">
                    <input type="text" class="form-control" 
                           id="triggerInput_${config.id}"
                           placeholder="请输入触发词">
                    <button class="btn btn-primary" type="button"
                            onclick="addTriggerWord('${config.id}')" title="添加触发词">
                        添加 <i class="bi bi-plus-lg"></i>
                    </button>
                </div>
                
                <div class="list-group" id="triggerList_${config.id}">
                    ${config.triggers.map((trigger, triggerIndex) => `
                        <div class="list-group-item d-flex justify-content-between align-items-center" data-trigger-index="${triggerIndex}">
                            ${trigger}
                            <button type="button" class="btn btn-danger btn-sm" 
                                    onclick="removeTriggerWordByIndex('${config.id}', ${triggerIndex})" 
                                    title="删除触发词">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        </div>
                    `).join('')}
                </div>
                
                ${config.triggers.length === 0 ? `
                    <div class="text-muted small mt-2">
                        <i class="bi bi-exclamation-triangle me-1"></i>
                        请至少添加一个触发词
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');
    
    // 更新添加按钮状态
    updateAddGroupChatButton();
}

// 获取人设选项（需要从现有的AVATAR_DIR选项中获取）
function getAvatarOptions(selectedValue = '') {
    const avatarSelect = document.querySelector('select[name="AVATAR_DIR"]');
    if (!avatarSelect) return '<option value="">暂无可用人设</option>';
    
    let options = '';
    for (let option of avatarSelect.options) {
        if (option.value) {
            const avatarName = option.value.split('/').pop();
            const selected = option.value === selectedValue ? 'selected' : '';
            options += `<option value="${option.value}" ${selected}>${avatarName}</option>`;
        }
    }
    return options || '<option value="">暂无可用人设</option>';
}

// 获取用户列表选项（从LISTEN_LIST中获取）
function getUserListOptions(selectedValue = '') {
    const userListElement = document.getElementById('selected_users_LISTEN_LIST');
    if (!userListElement) return '<option value="">暂无可用用户</option>';
    
    const userElements = userListElement.querySelectorAll('.list-group-item');
    let options = '';
    
    userElements.forEach(element => {
        const userName = element.textContent.trim().replace('×', '').trim();
        if (userName) {
            const selected = userName === selectedValue ? 'selected' : '';
            options += `<option value="${userName}" ${selected}>${userName}</option>`;
        }
    });
    
    return options || '<option value="">暂无可用用户</option>';
}

// 更新群聊配置字段
function updateGroupChatConfigField(configId, field, value) {
    const config = window.groupChatConfigs.find(c => c.id === configId);
    if (config) {
        config[field] = value;
        updateGroupChatConfigData();
    }
}

// 更新所有群聊配置中的群聊名称选择框
function updateGroupChatConfigSelects() {
    // 重新渲染群聊配置列表以更新选择框选项
    renderGroupChatConfigList();
}

// 添加触发词
function addTriggerWord(configId) {
    const input = document.getElementById(`triggerInput_${configId}`);
    const triggerWord = input.value.trim();
    
    if (!triggerWord) {
        alert('请输入触发词');
        return;
    }
    
    const config = window.groupChatConfigs.find(c => c.id === configId);
    if (config) {
        if (!config.triggers.includes(triggerWord)) {
            config.triggers.push(triggerWord);
            updateGroupChatConfigData();
            renderGroupChatConfigList();
            input.value = '';
        } else {
            alert('触发词已存在');
        }
    }
}

// 删除触发词
function removeTriggerWord(configId, triggerWord) {
    const config = window.groupChatConfigs.find(c => c.id === configId);
    if (config) {
        config.triggers = config.triggers.filter(t => t !== triggerWord);
        updateGroupChatConfigData();
        renderGroupChatConfigList();
    }
}

// 通过索引删除触发词
function removeTriggerWordByIndex(configId, triggerIndex) {
    const config = window.groupChatConfigs.find(c => c.id === configId);
    if (config && config.triggers[triggerIndex] !== undefined) {
        config.triggers.splice(triggerIndex, 1);
        updateGroupChatConfigData();
        renderGroupChatConfigList();
    }
}

// 删除群聊配置
function removeGroupChatConfig(configId) {
    if (confirm('确定要删除此群聊配置吗？')) {
        window.groupChatConfigs = window.groupChatConfigs.filter(c => c.id !== configId);
        updateGroupChatConfigData();
        renderGroupChatConfigList();
        updateAddGroupChatButton();
    }
}

// 更新隐藏字段的数据
function updateGroupChatConfigData() {
    const configInput = document.getElementById('GROUP_CHAT_CONFIG');
    if (configInput) {
        configInput.value = JSON.stringify(window.groupChatConfigs);
    }
}

// 更新添加群聊配置按钮状态
function updateAddGroupChatButton() {
    const addButton = document.getElementById('addGroupChatBtn');
    if (!addButton) return;
    
    if (window.groupChatConfigs.length >= 1) {
        addButton.disabled = true;
        addButton.classList.remove('btn-primary');
        addButton.classList.add('btn-secondary');
        addButton.innerHTML = '<i class="bi bi-check-lg me-1"></i>已达配置上限';
        addButton.title = '当前版本仅支持一个群聊配置';
    } else {
        addButton.disabled = false;
        addButton.classList.remove('btn-secondary');
        addButton.classList.add('btn-primary');
        addButton.innerHTML = '<i class="bi bi-plus-lg me-1"></i>添加群聊配置';
        addButton.title = '添加新的群聊配置';
    }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initGroupChatConfig, 500);
});