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

class SentimentAnalyzer:
    def __init__(self):
        self.emotion_dict = {}
        self.stopwords = set()
        self._load_emotion_dictionary()
        self._load_stopwords()

    def _load_stopwords(self):
        """加载中文停用词表"""
        with open('src/handlers/emodata/CNstopwords.txt', 'r', encoding='utf-8') as f:
            for line in f:
                word = line.strip()
                if word:
                    self.stopwords.add(word)
        print('中文停用词表加载完成')

    def _load_emotion_dictionary(self):
        """加载情感词典并构建快速查询结构"""
        df = pd.read_excel('src/handlers/emodata/大连理工大学中文情感词汇本体.xlsx')
        for _, row in df.iterrows():
            word = row['词语']
            category = row['情感分类']
            if category in CATEGORY_MAPPING:
                emotion_type, polarity = CATEGORY_MAPPING[category]
                self.emotion_dict[word] = (emotion_type, polarity)
        print('情感词典加载完成')

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
        word_counts = Counter(words)

        # 情感计数处理
        for word, count in word_counts.items():
            if word in self.emotion_dict:
                emotion_type, polarity = self.emotion_dict[word]
                
                # 更新极性计数
                counters[polarity] += count
                
                # 更新具体情感计数
                if emotion_type in counters:
                    counters[emotion_type] += count

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
        return {
            **emotion_result,
            'sentiment_score': self._get_sentiment_score(text)
        }

''''
# 使用示例
if __name__ == "__main__":
    analyzer = SentimentAnalyzer()
    test_text = "我非常开心的讨厌你"
    result = analyzer.analyze(test_text)
    print(result)
'''