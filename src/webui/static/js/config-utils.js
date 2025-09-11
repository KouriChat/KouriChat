// 配置工具函数
console.log('config-utils.js 已加载');

// 更新数值滑块的值
function updateRangeValue(key, value) {
    const display = document.getElementById(`${key}_display`);
    const input = document.getElementById(key);
    if (display) {
        display.textContent = value;
    }
    if (input) {
        input.value = value;
    }
}

// 全局统一updateTemperature函数 - 处理所有温度滑块
function updateTemperature(key, value) {
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

// 显示保存通知
function showSaveNotification(message, type = 'success') {
    const notification = document.getElementById('saveNotification');
    const messageElement = document.getElementById('saveNotificationMessage');

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

// 初始化所有开关滑块
function initializeSwitches() {
    // 获取所有开关滑块
    const switches = document.querySelectorAll('input[type="checkbox"][role="switch"]');
    switches.forEach(switchElem => {
        // 获取对应的标签
        const label = document.getElementById(switchElem.id + '_label');
        if (label) {
            // 更新标签文本
            label.textContent = switchElem.checked ? '启用' : '停用';
            console.log(`初始化开关 ${switchElem.id}: ${switchElem.checked ? '启用' : '停用'}`);
        }
    });
}

// 更新开关标签
function updateSwitchLabel(checkbox) {
    const label = document.getElementById(checkbox.id + '_label');
    if (label) {
        label.textContent = checkbox.checked ? '启用' : '停用';
    }

    // 在控制台输出当前状态，便于调试
    console.log(`${checkbox.id} 状态已更新为: ${checkbox.checked}`);
}