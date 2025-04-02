"""
感情处理模块
负责处理感情相关功能，包括:
- 文本正负向识别
- 文本主要感情分析
- 文本感情强烈程度评分
"""
import sys
from pathlib import Path
from functools import lru_cache
import math
import jieba
import pandas as pd
from collections import defaultdict
import logging

# 配置基础路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent.parent.parent))

# 获取 logger 实例
logger = logging.getLogger("main")

# 情感分类映射表
CATEGORY_MAPPING = {
    'PA': ('joy', 'positive'), 'PE': ('joy', 'positive'),
    'PD': ('like', 'positive'), 'PH': ('like', 'positive'),
    'PG': ('like', 'positive'), 'PB': ('like', 'positive'),
    'PK': ('like', 'positive'), 'PC': ('surprise', 'positive'),
    'NA': ('anger', 'negative'), 'NB': ('anger', 'negative'),
    'NJ': ('depress', 'negative'), 'NH': ('depress', 'negative'),
    'PF': ('depress', 'negative'), 'NI': ('fear', 'negative'),
    'NC': ('fear', 'negative'), 'NG': ('fear', 'negative'),
    'NE': ('dislike', 'negative'), 'ND': ('dislike', 'negative'),
    'NK': ('dislike', 'negative'), 'NL': ('dislike', 'negative'),
}

# 程度副词权重表
DEGREE_WEIGHTS = {
    '极其': 3.0, '超': 2.8, '最': 2.5, '非常': 2.0, '特别': 2.0,
    '十分': 2.0, '较为': 1.5, '比较': 1.5, '有点': 0.7, '稍微': 0.6, '略微': 0.5
}

def load_word_list(file_path):
    """加载词表文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        print(f"Warning: Missing lexicon file - {file_path}")
        return set()

class SentimentResourceLoader:
    """情感分析资源加载器"""
    def __init__(self):
        self.word_sentiment_dict = {}
        self.negative_words = set()
        self.degree_weights = DEGREE_WEIGHTS
        self.degree_adverbs = set(DEGREE_WEIGHTS.keys())
        self._load_resources()

    def _load_csv_fast(self, file_path):
        """优化CSV加载速度"""
        try:
            return pd.read_csv(
                file_path,
                usecols=['词语', '情感分类'],
                dtype={'词语': 'string', '情感分类': 'category'},
                engine='c'
            )
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return pd.DataFrame()

    def _load_resources(self):
        """加载所有词典资源"""
        # 加载大连理工情感词汇
        emotion_path = BASE_DIR / 'emodata' / '大连理工大学中文情感词汇本体.csv'
        df = self._load_csv_fast(emotion_path)
        if not df.empty:
            valid_entries = df[df['情感分类'].isin(CATEGORY_MAPPING)]
            self.word_sentiment_dict.update({
                row['词语']: CATEGORY_MAPPING[row['情感分类']]
                for _, row in valid_entries.iterrows()
            })

        # 合并扩展词表
        pos_neg_map = [
            (BASE_DIR/'emodata/正面情绪词.txt', ('joy', 'positive')),
            (BASE_DIR/'emodata/负面情绪词.txt', ('depress', 'negative'))
        ]
        for file_path, category in pos_neg_map:
            words = load_word_list(file_path)
            self.word_sentiment_dict.update({w: category for w in words})

        # 加载否定词
        self.negative_words = load_word_list(BASE_DIR/'emodata/否定词表.txt')

class SentimentAnalyzer:
    """情感分析器"""
    def __init__(self, resource_loader):
        self.res = resource_loader
        self._warm_up()
        
        # 将常用数据转为实例属性加速访问
        self.degree_adverbs = self.res.degree_adverbs
        self.negative_words = self.res.negative_words
        self.degree_weights = self.res.degree_weights
        
        # 添加：定义强攻击性/侮辱性词汇模式 (使用更通用的代表，实际应填充具体词汇)
        # 注意：这里的词汇仅为示例，需要根据实际情况填充或使用更复杂的匹配
        self.abusive_keywords = {"傻逼", "草泥马", "操你", "日你", "傻叉", "脑残", "垃圾", "废物", "滚蛋", "去死", "傻O", "草你O"} # 示例

    def _warm_up(self):
        """预热关键组件"""
        jieba.lcut("预热加载", cut_all=False, HMM=False)

    @lru_cache(maxsize=10000)
    def _get_sentiment(self, word):
        """带缓存的情感属性查询"""
        return self.res.word_sentiment_dict.get(word, (None, None))

    def analyze(self, text):
        """执行情感分析"""
        words = jieba.lcut(text, cut_all=False, HMM=False)
        emotion_counts = defaultdict(float)
        current_negation = False
        current_weight = 1.0
        total_words = len(words)
        abusive_detected = False

        # 将常用方法转为局部变量加速访问
        degree_adverbs = self.degree_adverbs
        negative_words = self.negative_words
        get_sentiment = self._get_sentiment

        for i, word in enumerate(words):
            if word in {'，', '。', '！', '？', '；', ':', '!', '?', ';'}:
                current_negation = False
                current_weight = 1.0
                continue

            # 处理程度副词
            if word in degree_adverbs:
                current_weight = self.degree_weights.get(word, 1.0)
                continue

            # 处理否定词
            if word in negative_words:
                current_negation = not current_negation
                emotion_counts['negative'] += 1.5 * (1.2 - i/total_words)
                continue
                
            # 添加：检测攻击性/侮辱性词汇
            if word in self.abusive_keywords:
                logger.warning(f"检测到攻击性词汇: {word}")
                abusive_detected = True
                # 降低分数提升幅度
                emotion_counts['anger'] += 2.5
                emotion_counts['negative'] += 2.5
                break

            # 情感词处理
            emotion_type, polarity = get_sentiment(word)
            if emotion_type:
                if current_negation:
                    polarity = 'negative' if polarity == 'positive' else 'positive'
                    emotion_type = self._reverse_emotion(emotion_type)
                
                pos_weight = current_weight * (1.2 - 0.5*(i/total_words))
                emotion_counts[polarity] += pos_weight
                emotion_counts[emotion_type] += pos_weight
                current_weight = 1.0

        return self._compute_result(emotion_counts, total_words)

    def _compute_result(self, counts, text_len):
        """计算最终结果"""
        positive = counts.get('positive', 0.0)
        negative = counts.get('negative', 0.0)
        total_emotion = sum(v for k,v in counts.items() if k not in ['positive','negative'])
        text_len = max(text_len, 1)

        intensity = total_emotion / text_len
        log_intensity = math.log1p(intensity * 100)
        final_intensity = math.tanh(log_intensity / 3)
        
        # 如果检测到攻击性词汇，调整强度下限
        if abusive_detected:
            final_intensity = max(final_intensity, 0.6)
            logger.info(f"因检测到攻击性词汇，调整强度下限为 0.6，最终强度: {final_intensity:.2f}")

        if final_intensity < 0.15 or abs(positive - negative) < 0.1:
            # 即便强度低，如果检测到攻击性词汇，也应判定为负面/愤怒
            if abusive_detected:
                logger.info("检测到攻击性词汇，即使强度低也判定为愤怒/负面")
                return {
                   'sentiment_type': 'Anger', # 强制为愤怒
                   'polarity': '负面',
                   'sentiment_score': -5.0, # 强制负分
                   'intensity': round(final_intensity, 2)
                }
            # 原有中性判断逻辑
            return {
                'sentiment_type': 'Neutral',
                'polarity': '中立',
                'sentiment_score': 0.0,
                'intensity': round(final_intensity, 2)
            }

        direction = 1 if (positive - negative) > 0 else -1
        score = direction * final_intensity * 5
        
        # 添加：如果检测到攻击性词汇，确保结果是愤怒/负面
        if abusive_detected:
            main_emotion = 'Anger' # 强制主要情感为愤怒
            polarity_text = '负面'
            final_score = min(score, -abs(final_intensity * 5)) # 确保是负分
            logger.info(f"攻击性词汇覆盖情感判断: {main_emotion}, {polarity_text}, {final_score:.2f}")
            return {
                'sentiment_type': main_emotion,
                'polarity': polarity_text,
                'sentiment_score': round(final_score, 2),
                'intensity': round(final_intensity, 2)
            }

        # 原有逻辑计算主要情感和得分
        return {
            'sentiment_type': self._get_main_emotion(counts),
            'polarity': '正面' if direction > 0 else '负面',
            'sentiment_score': round(score, 2),
            'intensity': round(final_intensity, 2)
        }

    def _get_main_emotion(self, counts):
        """确定主要情感类型（保持原有逻辑）"""
        emotions = [k for k in counts if k not in ['positive','negative']]
        if not emotions:
            return 'Neutral'
        main_emo = max(emotions, key=lambda x: counts[x])
        return main_emo.capitalize() if counts[main_emo] > 0 else 'Neutral'

    def _reverse_emotion(self, emotion):
        """情感反转逻辑（保持原有逻辑）"""
        reversal_map = {
            'joy': 'depress', 'like': 'dislike',
            'surprise': 'fear', 'anger': 'calm',
            'dislike': 'like', 'fear': 'surprise',
            'depress': 'joy'
        }
        return reversal_map.get(emotion, emotion)

# 使用示例
if __name__ == "__main__":
    # 初始化资源加载器（全局只需一次）
    resource_loader = SentimentResourceLoader()
    
    # 创建分析器实例
    analyzer = SentimentAnalyzer(resource_loader)

    test_cases = [
        "这个产品简直完美到不可思议！",
        "服务态度极其糟糕，非常失望。",
        "东西一般般，没什么特别感觉。"
    ]
    
    for text in test_cases:
        result = analyzer.analyze(text)
        print(f"文本: {text}")
        print(f"结果: {result}\n")