import os
import logging
import random
from typing import List
from datetime import datetime
from src.services.ai.llm_service import LLMService
import jieba

logger = logging.getLogger('main')

# 定义需要重点关注的关键词列表
KEYWORDS = [
    "记住了没？", "记好了", "记住", "别忘了", "牢记", "记忆深刻", "不要忘记", "铭记",
    "别忘掉", "记在心里", "时刻记得", "莫失莫忘", "印象深刻", "难以忘怀", "念念不忘", "回忆起来",
    "永远不忘", "留意", "关注", "提醒", "提示", "警示", "注意", "特别注意",
    "记得检查", "请记得", "务必留意", "时刻提醒自己", "定期回顾", "随时注意", "不要忽略", "确认一下",
    "核对", "检查", "温馨提示", "小心"
]


class MemoryHandler:
    def __init__(self, root_dir: str, api_key: str, base_url: str, model: str,
                 max_token: int, temperature: float, max_groups: int):
        # 保持原有初始化参数
        self.root_dir = root_dir
        self.memory_dir = os.path.join(root_dir, "data", "memory")
        self.short_memory_path = os.path.join(self.memory_dir, "short_memory.txt")
        self.long_memory_buffer_path = os.path.join(self.memory_dir, "long_memory_buffer.txt")
        self.high_priority_memory_path = os.path.join(self.memory_dir, "high_priority_memory.txt") # 新增
        self.api_key = api_key
        self.base_url = base_url
        self.max_token = max_token
        self.temperature = temperature
        self.max_groups = max_groups
        self.model = model

        # 新增记忆层
        self.memory_layers = {
            'working': os.path.join(self.memory_dir, "working_memory.txt")
        }

        # 初始化文件和目录
        os.makedirs(self.memory_dir, exist_ok=True)
        self._init_files()

        # 新增：情感权重
        self.emotion_weights = {
            'neutral': 1,
            'happy': 2,
            'sad': 2,
            'anger': 3,  # 愤怒情绪权重更高
            'surprise': 2,
            'fear': 2,
            'disgust': 2,
        }

        # 新增： 消息重复计数
        self.memory_counts = {}

    def _init_files(self):
        """初始化所有记忆文件"""
        files_to_check = [
            self.short_memory_path,
            self.long_memory_buffer_path,
            self.high_priority_memory_path, # 新增
            *self.memory_layers.values()
        ]
        for f in files_to_check:
            if not os.path.exists(f):
                with open(f, "w", encoding="utf-8") as _:
                    logger.info(f"创建文件: {os.path.basename(f)}")

    def _get_deepseek_client(self):
        """获取LLM客户端（保持原有逻辑）"""
        return LLMService(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
            max_token=self.max_token,
            temperature=self.temperature,
            max_groups=self.max_groups
        )

    def add_short_memory(self, message: str, reply: str):
        """添加短期记忆（兼容原有调用）"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            logger.debug(f"开始写入短期记忆文件: {self.short_memory_path}")
            with open(self.short_memory_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] 用户: {message}\n")
                f.write(f"[{timestamp}] bot: {reply}\n\n")
            logger.info(f"成功写入短期记忆: 用户 - {message}, bot - {reply}")
        except Exception as e:
            logger.error(f"写入短期记忆文件失败: {str(e)}", exc_info=True)

        # 检查是否包含关键词, 并获取情感
        emotion = self._detect_emotion(message)
        if any(keyword in message for keyword in KEYWORDS) or emotion != 'neutral':
            self._add_high_priority_memory(message, emotion) # 传入 emotion

        # 增加消息的重复计数 (这里为了简化，直接使用原消息作为 key)
        if message in self.memory_counts:
            self.memory_counts[message] += 1
        else:
            self.memory_counts[message] = 1
        logger.info(f"消息 '{message}' 的重复计数: {self.memory_counts[message]}")

    def _add_high_priority_memory(self, message: str, emotion: str): # 修改
        """添加高优先级记忆"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            high_priority_path = os.path.join(self.memory_dir, "high_priority_memory.txt")
            logger.info(f"开始写入高优先级记忆文件: {high_priority_path}")
            with open(high_priority_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] 情感: {emotion}, 消息: {message}\n") # 写入情感
            logger.info(f"成功写入高优先级记忆: {message}")
        except Exception as e:
            logger.error(f"写入高优先级记忆文件失败: {str(e)}", exc_info=True)

    def _detect_emotion(self, text: str) -> str:
        """基于词典的情感分析"""

        # 加载情感词典
        positive_words = self._load_wordlist('src/handlers/emodata/正面情绪词.txt')
        negative_words = self._load_wordlist('src/handlers/emodata/负面情绪词.txt')
        negation_words = self._load_wordlist('src/handlers/emodata/否定词表.txt')
        degree_words = self._load_wordlist('src/handlers/emodata/程度副词.txt')
        
        # 修正程度副词
        degree_dict = {}
        for word in degree_words:
            parts = word.strip().split(',')  # 假设格式为 "词语,权重"
            if len(parts) == 2:
                degree_dict[parts[0].strip()] = float(parts[1].strip())

        # 分词
        words = list(jieba.cut(text))

        # 情感计算
        score = 0
        negation_count = 0  # 否定词计数
        for i, word in enumerate(words):
            if word in positive_words:
                # 考虑程度副词
                degree = 1.0
                for j in range(i - 1, max(-1, i - 4), -1):  # 向前查找最多3个词
                    if words[j] in degree_dict:
                        degree *= degree_dict[words[j]]
                        break
                # 考虑否定词
                if negation_count % 2 == 1:
                    degree *= -1.0
                score += degree

            elif word in negative_words:
                degree = 1.0
                for j in range(i - 1, max(-1, i - 4), -1):
                    if words[j] in degree_dict:
                        degree *= degree_dict[words[j]]
                        break

                if negation_count % 2 == 1:
                    degree *= -1.0
                score -= degree

            elif word in negation_words:
                negation_count += 1

        # 情感分类
        if score > 0.5:
            return 'happy'
        elif score < -0.5:
            return 'anger' # 负面情绪比较强烈
        elif -0.5 <= score <= 0.5:
            return 'neutral'
        else:
            return 'sad' # 负面情绪

    def _load_wordlist(self, filepath: str) -> List[str]:
        """加载词表文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"加载词表文件失败: {filepath} - {str(e)}")
            return []

    def summarize_memories(self):
        """总结短期记忆到长期记忆（保持原有逻辑）"""
        if not os.path.exists(self.short_memory_path):
            logger.debug("短期记忆文件不存在，跳过总结")
            return

        with open(self.short_memory_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) >= 30:  # 15组对话
            max_retries = 3  # 最大重试次数
            retries = 0
            while retries < max_retries:
                try:
                    deepseek = self._get_deepseek_client()
                    # 优化提示，更明确地指示LLM考虑情感和重复
                    prompt = (
                        "请将以下对话记录总结为最重要的几条长期记忆，总结内容应包含地点，事件，人物（如果对话记录中有的话）用中文简要表述。\n"
                        "注意：请特别关注以下几点：\n"
                        "1. 具有强烈情感的消息（如愤怒、高兴）应优先考虑。\n"
                        "2. 被多次提及的消息应优先考虑。\n"
                        "3. 包含关键词（如 '记住'、'别忘了' 等）的消息应优先考虑。\n\n"
                        "对话记录：\n" + "".join(lines[-30:])
                    )
                    summary = deepseek.get_response(
                        message=prompt,
                        user_id="system",
                        system_prompt="总结以下对话："  # 可以保留之前的 system_prompt
                    )
                    logger.debug(f"总结结果:\n{summary}")

                    # 检查是否需要重试
                    retry_sentences = [
                        "好像有些小状况，请再试一次吧～",
                        "信号好像不太稳定呢（皱眉）",
                        "思考被打断了，请再说一次好吗？"
                    ]
                    if summary in retry_sentences:
                        logger.warning(f"收到需要重试的总结结果: {summary}")
                        retries += 1
                        continue

                    # 写入长期记忆缓冲区
                    date = datetime.now().strftime('%Y-%m-%d')
                    try:
                        logger.debug(f"开始写入长期记忆缓冲区文件: {self.long_memory_buffer_path}")
                        with open(self.long_memory_buffer_path, "a", encoding="utf-8") as f:
                            f.write(f"总结日期: {date}\n")
                            f.write(summary + "\n\n")
                        logger.info(f"成功将总结结果写入长期记忆缓冲区: {summary}")
                    except Exception as e:
                        logger.error(f"写入长期记忆缓冲区文件失败: {str(e)}", exc_info=True)

                    # 清空短期记忆
                    try:
                        logger.debug(f"开始清空短期记忆文件: {self.short_memory_path}")
                        open(self.short_memory_path, "w").close()
                        logger.info("记忆总结完成，已写入长期记忆缓冲区，短期记忆已清空")
                    except Exception as e:
                        logger.error(f"清空短期记忆文件失败: {str(e)}", exc_info=True)
                    break  # 成功后退出循环

                except Exception as e:
                    logger.error(f"记忆总结失败: {str(e)}")
                    retries += 1
                    if retries >= max_retries:
                        logger.error("达到最大重试次数，放弃总结")
                        break

    def get_relevant_memories(self, query: str) -> List[str]:
        """获取相关记忆（增加调试日志）"""
        if not os.path.exists(self.long_memory_buffer_path):
            logger.warning("长期记忆缓冲区不存在，尝试创建...")
            try:
                with open(self.long_memory_buffer_path, "w", encoding="utf-8"):
                    logger.info("长期记忆缓冲区文件已创建。")
            except Exception as e:
                logger.error(f"创建长期记忆缓冲区文件失败: {str(e)}")
                return []

        # 调试：打印文件路径
        logger.debug(f"长期记忆缓冲区文件路径: {self.long_memory_buffer_path}")

        max_retries = 3  # 设置最大重试次数
        for retry_count in range(max_retries):
            try:
                with open(self.long_memory_buffer_path, "r", encoding="utf-8") as f:
                    memories = [line.strip() for line in f if line.strip()]

                # 调试：打印文件内容
                logger.debug(f"长期记忆缓冲区条目数: {len(memories)}")

                if not memories:
                    logger.debug("长期记忆缓冲区为空")
                    return []

                deepseek = self._get_deepseek_client()
                response = deepseek.get_response(
                    message="\n".join(memories[-20:]),
                    user_id="retrieval",
                    system_prompt=f"请从以下记忆中找到与'{query}'最相关的条目，按相关性排序返回最多3条:"
                )

                # 调试：打印模型响应
                logger.debug(f"模型返回相关记忆条数: {len(response.splitlines())}")

                # 检查是否需要重试
                retry_sentences = [
                    "好像有些小状况，请再试一次吧～",
                    "信号好像不太稳定呢（皱眉）",
                    "思考被打断了，请再说一次好吗？"
                ]
                if response in retry_sentences:
                    if retry_count < max_retries - 1:
                        logger.warning(f"第 {retry_count + 1} 次重试：收到需要重试的响应: {response}")
                        continue  # 重试
                    else:
                        logger.error(f"达到最大重试次数：最后一次响应为 {response}")
                        return []
                else:
                    # 返回处理后的响应
                    return [line.strip() for line in response.split("\n") if line.strip()]

            except Exception as e:
                logger.error(f"第 {retry_count + 1} 次尝试失败: {str(e)}")
                if retry_count < max_retries - 1:
                    continue
                else:
                    logger.error(f"达到最大重试次数: {str(e)}")
                return []

        return []

    def maintain_memories(self, max_entries=100):
        """记忆文件维护"""
        # 长期记忆轮替
        if os.path.getsize(self.long_memory_buffer_path) > 1024 * 1024:  # 1MB
            try:
                logger.debug(f"开始维护长期记忆缓冲区文件: {self.long_memory_buffer_path}")
                with open(self.long_memory_buffer_path, 'r+', encoding='utf-8') as f:
                    lines = f.readlines()
                    keep_lines = lines[-max_entries * 2:]  # 保留最后N条
                    f.seek(0)
                    f.writelines(keep_lines)
                    f.truncate()
                logger.info("已完成长期记忆维护")
            except Exception as e:
                logger.error(f"长期记忆维护失败: {str(e)}", exc_info=True)

# 测试模块
if __name__ == "__main__":
    # 配置日志格式
    logging.basicConfig(
        level=logging.DEBUG,  # 调整为 DEBUG 级别，以便查看调试信息
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 测试配置
    test_config = {
        "root_dir": os.path.dirname(os.path.abspath(".")),  # 测试数据目录，往上一个根目录寻址
        "api_key": "",  # 测试用的API Key
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "max_token": 512,
        "temperature": 0.7,
        "max_groups": 5
    }

    # 增强的清理函数
    def clean_test_files():
        files_to_clean = [
            os.path.join(test_config["root_dir"], "data", "memory", f)
            for f in ['short_memory.txt',
                      'long_memory_buffer.txt',
                      'instant_memory.txt',
                      'working_memory.txt',
                      'high_priority_memory.txt']
        ]

        for path in files_to_clean:
            if os.path.exists(path):
                try:
                    if path.endswith('working_memory.txt'):
                        # 保留工作记忆模板
                        with open(path, 'w', encoding='utf-8') as f:
                            f.write("初始工作记忆内容...\n")
                    else:
                        os.remove(path)
                    logger.info(f"清理文件: {os.path.basename(path)}")
                except Exception as e:
                    logger.error(f"清理文件失败: {path} - {str(e)}")


    clean_test_files()  # 替换原有的单个清理操作

    # 初始化 MemoryHandler
    logger.info("初始化 MemoryHandler...")
    handler = MemoryHandler(**test_config)

    # 测试情感分析函数
    logger.info("测试情感分析函数...")
    test_cases = {
        "今天天气真好！": "happy",
        "我非常生气！": "anger",
        "这部电影很无聊。": "sad",
        "一切都还好。": "neutral",
        "我好难过，但是又有一点开心。": "neutral",  # 复杂情感
        "我不太喜欢这个。": "sad", # 否定+轻微负面
        "超级开心！": "happy", # 程度副词
        "不是很好": "sad", # 否定
        "非常非常非常好！": "happy" # 多个程度副词
    }
    for text, expected_emotion in test_cases.items():
        detected_emotion = handler._detect_emotion(text)
        if detected_emotion == expected_emotion:
            logger.info(f"测试通过：'{text}' -> 预期: {expected_emotion}, 实际: {detected_emotion}")
        else:
            logger.error(f"测试失败：'{text}' -> 预期: {expected_emotion}, 实际: {detected_emotion}")

    # 测试添加短期记忆
    logger.info("测试添加短期记忆...")
    handler.add_short_memory("记住我喜欢吃巧克力蛋糕", "好的，我记住了！")
    handler.add_short_memory("今天工作好累！", "要注意休息哦~")
    handler.add_short_memory("我生气了！", "冷静一下~")
    handler.add_short_memory("今天很开心！", "太好了！")
    handler.add_short_memory("明天要去旅行，好期待！", "祝您旅途愉快！")
    handler.add_short_memory("最近在学习编程，感觉有点难", "慢慢来，编程需要耐心和练习。")
    handler.add_short_memory("我养了一只小猫，它很可爱", "小猫确实很可爱，记得照顾好它哦~")
    handler.add_short_memory("最近天气变冷了", "记得多穿点衣服，别感冒了。")
    handler.add_short_memory("我喜欢看电影，尤其是科幻片", "科幻片很有趣，您最近看了什么好片？")
    handler.add_short_memory("我有点饿了", "要不要吃点东西？记得选择健康的食物。")

    # 测试总结记忆
    logger.info("测试总结记忆...")
    handler.summarize_memories()

    # 测试获取相关记忆
    logger.info("测试获取相关记忆...")
    relevant_memories = handler.get_relevant_memories("工作")
    logger.info(f"获取到的相关记忆: {relevant_memories}")

    # 手动验证长期记忆缓冲区文件内容
    long_memory_buffer_path = os.path.join(test_config["root_dir"], "data", "memory", "long_memory_buffer.txt")
    with open(long_memory_buffer_path, "r", encoding="utf-8") as f:
        logger.info("长期记忆缓冲区文件内容:")
        logger.info(f.read())

    # 测试瞬时记忆（如果存在）
    # logger.info("测试瞬时记忆功能...")
    # handler.add_short_memory("我生气了！", "冷静一下~")
    # handler.add_short_memory("今天很开心！", "太好了！")

    # 打印瞬时记忆文件内容（如果存在）
    # instant_memory_path = os.path.join(test_config["root_dir"], "data", "memory", "instant_memory.txt")
    # with open(instant_memory_path, "r", encoding="utf-8") as f:
    #     logger.info("瞬时记忆文件内容:")
    #     logger.info(f.read())

    # 添加工作记忆 (如果存在)
    working_memory_path = os.path.join(test_config["root_dir"], "data", "memory", "working_memory.txt")
    logger.info("测试工作记忆功能...")
    try:
        logger.debug(f"开始写入工作记忆文件: {working_memory_path}")
        with open(working_memory_path, "w", encoding="utf-8") as f:
            f.write("2025-03-08 19:30:00 - 今日小结：\n")
            f.write("1. 用户多次表达工作疲劳，建议其注意休息。\n")
            # 接上段代码
            f.write("2. 用户喜欢巧克力蛋糕，已经记住这一偏好。\n")
            f.write("3. 用户在情绪波动时，提醒用户保持冷静。\n")
            f.write("4. 用户计划去旅行，祝其旅途愉快。\n")
            f.write("5. 用户在学习编程，鼓励其保持耐心。\n")
            f.write("6. 用户养了一只小猫，提醒其照顾好宠物。\n")
            f.write("7. 用户提到天气变冷，建议其注意保暖。\n")
            f.write("8. 用户喜欢看电影，尤其是科幻片。\n")
            f.write("9. 用户感到饿了，建议其选择健康食物。\n\n")
            f.write("关键记忆标签：\n")
            f.write("- 用户过敏史：无\n")
            f.write("- 用户喜好：巧克力蛋糕、科幻电影\n")
            f.write("- 用户宠物：小猫\n")
            f.write("- 用户近期计划：旅行\n")
        logger.info("成功写入工作记忆文件")
    except Exception as e:
        logger.error(f"写入工作记忆文件失败: {str(e)}")

    # 打印工作记忆文件内容
    with open(working_memory_path, "r", encoding="utf-8") as f:
        logger.info("工作记忆文件内容:")
        logger.info(f.read())

        # 打印高优先级记忆文件内容
    high_priority_path = os.path.join(test_config["root_dir"], "data", "memory", "high_priority_memory.txt")
    if os.path.exists(high_priority_path):
        with open(high_priority_path, "r", encoding="utf-8") as f:
            logger.info("高优先级记忆文件内容:")
            logger.info(f.read())
