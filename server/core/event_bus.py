import asyncio
from typing import Dict, List, Callable, Any, Coroutine
from concurrent.futures import ThreadPoolExecutor

class EventBus:
    def __init__(self):
        """
        初始化事件总线
        subscribers: 用于存储事件类型及其对应的订阅者回调函数
        routes: 用于存储事件路由规则
        executor: 线程池执行器，用于处理同步回调
        """
        self.subscribers: Dict[str, List[Callable]] = {}
        self.routes: Dict[str, str] = {} 
        self.executor = ThreadPoolExecutor()
        self.loop = asyncio.get_event_loop()

    def add_route(self, source_event: str, target_event: str):
        """
        添加事件路由规则
        Args:
            source_event: 源事件类型
            target_event: 目标事件类型
        """
        self.routes[source_event] = target_event

    async def publish(self, event_type: str, event_data: Any):
        """
        异步发布事件
        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        # 检查是否存在路由规则
        if event_type in self.routes:
            event_type = self.routes[event_type]

        if event_type in self.subscribers:
            tasks = []
            for callback in self.subscribers[event_type]:
                if asyncio.iscoroutinefunction(callback):
                    # 异步回调直接创建任务
                    tasks.append(self.loop.create_task(callback(event_data)))
                else:
                    # 同步回调使用线程池执行
                    tasks.append(
                        self.loop.run_in_executor(
                            self.executor, 
                            callback, 
                            event_data
                        )
                    )
            # 等待所有任务完成
            await asyncio.gather(*tasks)

    def subscribe(self, event_type: str, callback: Callable):
        """
        订阅事件
        Args:
            event_type: 事件类型
            callback: 回调函数，可以是同步或异步函数
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    async def unsubscribe(self, event_type: str, callback: Callable):
        """
        取消订阅事件
        Args:
            event_type: 事件类型
            callback: 要取消的回调函数
        """
        if event_type in self.subscribers:
            self.subscribers[event_type].remove(callback)
            if not self.subscribers[event_type]:
                del self.subscribers[event_type]

    async def close(self):
        """
        关闭事件总线，清理资源
        """
        self.executor.shutdown(wait=True)



"""
使用示例：
"""

async def example():
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 添加路由规则
    event_bus.add_route("user_input", "message_process")
    
    # 异步处理函数
    async def async_handler(data):
        await asyncio.sleep(1)
        print(f"Async handled: {data}")
    
    # 同步处理函数
    def sync_handler(data):
        print(f"Sync handled: {data}")
    
    # 订阅事件
    event_bus.subscribe("message_process", async_handler)
    event_bus.subscribe("message_process", sync_handler)
    
    # 发布事件
    await event_bus.publish("user_input", "Hello World")
    
    # 清理资源
    await event_bus.close()


asyncio.run(example())
