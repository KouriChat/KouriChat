// 简单的本地访问统计
(function() {
    // 基本统计数据结构
    const stats = {
        pageViews: 0,
        startTime: Date.now(),
        events: []
    };

    // 记录页面访问
    function recordPageView() {
        stats.pageViews++;
        stats.events.push({
            type: 'pageview',
            timestamp: Date.now(),
            path: window.location.pathname
        });
        
        // 将统计数据保存到 localStorage
        try {
            localStorage.setItem('kouri_analytics', JSON.stringify(stats));
        } catch (e) {
            console.warn('无法保存统计数据到 localStorage');
        }
    }

    // 页面加载完成时记录访问
    window.addEventListener('load', recordPageView);

    // 提供全局访问接口
    window.kouriAnalytics = {
        getStats: () => stats,
        recordEvent: (eventName, data) => {
            stats.events.push({
                type: eventName,
                timestamp: Date.now(),
                data: data
            });
        }
    };
})(); 