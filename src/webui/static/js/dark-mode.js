// 护眼模式管理
class DarkModeManager {
    constructor() {
        // 确保只创建一个实例
        if (DarkModeManager.instance) {
            return DarkModeManager.instance;
        }
        DarkModeManager.instance = this;

        // 等待 DOM 加载完成
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }

    init() {
        // 立即应用存储的状态
        this.applyStoredState();
        
        // 使用事件委托监听切换
        document.addEventListener('change', (e) => {
            const toggle = e.target.closest('[data-dark-toggle]');
            if (toggle) {
                this.toggle(toggle.checked);
                e.preventDefault();
            }
        });

        // 监听系统主题变化
        window.matchMedia('(prefers-color-scheme: dark)').addListener((e) => {
            this.toggle(e.matches);
        });
    }

    applyStoredState() {
        const darkMode = localStorage.getItem('darkMode') === 'true';
        this.setDarkMode(darkMode);
    }

    setDarkMode(isDark) {
        const theme = isDark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', theme);
        document.body.setAttribute('data-bs-theme', theme);
        localStorage.setItem('darkMode', isDark);
        this.syncToggleState(isDark);
    }

    toggle(forcedState = null) {
        const currentState = document.documentElement.getAttribute('data-bs-theme') === 'dark';
        const newState = forcedState !== null ? forcedState : !currentState;
        this.setDarkMode(newState);
    }

    syncToggleState(isDark) {
        document.querySelectorAll('[data-dark-toggle]').forEach(toggle => {
            if (toggle.type === 'checkbox') {
                toggle.checked = isDark;
            }
        });
    }
}

// 立即创建实例
const darkMode = new DarkModeManager();

// 导出实例供其他模块使用
window.darkMode = darkMode; 