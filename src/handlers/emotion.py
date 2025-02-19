"""
感情处理模块
负责处理感情相关功能，包括:
- 文本情感分析
- 文本情感评估
- 文本感情七维分布
"""
import pandas as pd
import jieba
from snownlp import SnowNLP
from collections import Counter

# 情感分类到情感类型和极性的映射关系
CATEGORY_MAPPING = {
    # 喜悦（正面）
    'PA': ('joy', 'positive'),
    'PE': ('joy', 'positive'),
    # 喜好（正面）
    'PD': ('like', 'positive'),
    'PH': ('like', 'positive'),
    'PG': ('like', 'positive'),
    'PB': ('like', 'positive'),
    'PK': ('like', 'positive'),
    # 惊讶（正面）
    'PC': ('surprise', 'positive'),
    # 愤怒（负面）
    'NA': ('anger', 'negative'),
    # 低落（负面）
    'NB': ('depress', 'negative'),
    'NJ': ('depress', 'negative'),
    'NH': ('depress', 'negative'),
    'PF': ('depress', 'negative'),
    # 恐惧（负面）
    'NI': ('fear', 'negative'),
    'NC': ('fear', 'negative'),
    'NG': ('fear', 'negative'),
    # 厌恶（负面）
    'NE': ('dislike', 'negative'),
    'ND': ('dislike', 'negative'),
    'NN': ('dislike', 'negative'),
    'NK': ('dislike', 'negative'),
    'NL': ('dislike', 'negative')
}

class SentimentAnalyzer:
    def __init__(self):
        self.emotion_dict = {}
        self.stopwords = set()
        self.negation_words = set()  # 新增否定词集合
        self._load_emotion_dictionary()
        self._load_stopwords()
        self._load_negation_words()  # 加载否定词表

    def _load_negation_words(self):
        """加载否定词表"""
        with open('src/handlers/emodata/否定词.txt', 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    self.negation_words.add(word)
        print('否定词表加载完成')

    def _analyze_emotion(self, text):
        """核心情感分析方法"""
        counters = {
            'positive': 0,
            'negative': 0,
            'anger': 0,
            'dislike': 0,
            'fear': 0,
            'depress': 0,
            'surprise': 0,
            'like': 0,
            'joy': 0
        }

        # 分词并过滤停用词
        words = [word for word in jieba.lcut(text) if word not in self.stopwords]

        # 情感计数处理
        negation_flag = False
        for word in words:
            if word in self.negation_words:
                negation_flag = True
            elif word in self.emotion_dict:
                emotion_type, polarity = self.emotion_dict[word]
                if negation_flag:
                    # 反转极性
                    polarity = 'positive' if polarity == 'negative' else 'negative'
                    negation_flag = False

                # 更新极性计数
                counters[polarity] += 1

                # 更新具体情感计数
                if emotion_type in counters:
                    counters[emotion_type] += 1

        # 确定情感极性
        if counters['positive'] > counters['negative']:
            polarity = '正面'
        elif counters['positive'] == counters['negative']:
            polarity = '中立'
        else:
            polarity = '负面'

        # 确定主要情感类型
        emotion_fields = ['anger', 'dislike', 'fear', 'depress', 'surprise', 'like', 'joy']
        emotion_values = [(field, counters[field]) for field in emotion_fields]
        main_emotion, max_count = max(emotion_values, key=lambda x: x[1])

        return {
            'sentiment_type': main_emotion.capitalize() if max_count > 0 else 'None',
            'polarity': polarity,
            'emotion_info': {
                'length': len(words),
                'positive': counters['positive'],
                'negative': counters['negative'],
                **{k: v for k, v in counters.items() if k not in ['positive', 'negative']}
            }
        }

    def _get_sentiment_score(self, text):
        """获取SnowNLP情感评分"""
        return SnowNLP(text).sentiments

    def analyze(self, text):
        """综合分析方法"""
        emotion_result = self._analyze_emotion(text)
        raw_score = self._get_sentiment_score(text)
        
        # 根据极性调整符号位
        polarity = emotion_result['polarity']
        adjusted_score = raw_score
        if polarity == '正面':
            adjusted_score += 1
        elif polarity == '负面':
            adjusted_score -= 1
        
        return {
            **emotion_result,
            'sentiment_score': adjusted_score
        }


# 使用示例
if __name__ == "__main__":
    analyzer = SentimentAnalyzer()
    test_text = "今天打英雄联盟被sb队友气死了，但是晚上跟原p对线好爽"
    result = analyzer.analyze(test_text)
    print(result)
