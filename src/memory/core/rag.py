import re

import numpy as np
import faiss
from abc import ABC, abstractmethod
from typing import List, Optional
import openai
from openai import OpenAI
from sentence_transformers import SentenceTransformer, CrossEncoder

"""
本文件依赖安装
pip install sentence-transformers faiss-cpu numpy openai
如果使用在线模型需要额外安装openai等对应SDK
"""


class EmbeddingModel(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        pass


class LocalEmbeddingModel(EmbeddingModel):
    def __init__(self, model_path: str):
        self.model = SentenceTransformer(model_path)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_tensor=False).tolist()


class OnlineEmbeddingModel(EmbeddingModel):
    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):  # 参数名与调用处统一
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url  # 参数名改为base_url
        self.client = OpenAI(
            base_url=self.base_url,  # 使用统一参数名
            api_key=self.api_key
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings = []
        for text in texts:
            if not text.strip():
                embeddings.append([])
                continue

            for attempt in range(3):  # 最多重试3次
                try:
                    response = self.client.embeddings.create(
                        model=self.model_name,
                        input=text,
                        encoding_format="float"
                    )

                    # 强化响应校验
                    if not response or not response.data:
                        raise ValueError("API返回空响应")

                    embedding = response.data[0].embedding
                    if not isinstance(embedding, list) or len(embedding) == 0:
                        raise ValueError("无效的嵌入格式")

                    embeddings.append(embedding)
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"嵌入失败（已重试3次）: {str(e)}")
                        embeddings.append([0.0] * 1024)  # 返回默认维度向量
                    import time
                    time.sleep(1)  # 重试间隔
        return embeddings


class ReRanker(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        pass


class CrossEncoderReRanker(ReRanker):
    def __init__(self, model_path: str):
        self.model = CrossEncoder(model_path)

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        pairs = [[query, doc] for doc in documents]
        return self.model.predict(pairs).tolist()


class OnlineCrossEncoderReRanker(ReRanker):
    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        scores = []
        for doc in documents:
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system",
                         "content": "您是一个帮助评估文档与查询相关性的助手。请仅返回一个0到1之间的浮点数，不要包含其他文本。"},
                        {"role": "user", "content": f"查询：{query}\n文档：{doc}\n请评估该文档与查询的相关性分数（0-1）："}
                    ]
                )
                content = response.choices[0].message.content.strip()
                # 使用正则表达式提取数值
                match = re.search(r"0?\.\d+|\d\.?\d*", content)
                if match:
                    score = float(match.group())
                    score = max(0.0, min(1.0, score))  # 确保分数在0-1之间
                else:
                    score = 0.0  # 解析失败默认值
            except Exception as e:
                score = 0.0  # 异常处理
            scores.append(score)
        return scores


class RAG:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None or not kwargs.get('singleton', True):
            cls._instance = super(RAG, cls).__new__(cls)
        return cls._instance

    def __init__(self,
                 embedding_model: EmbeddingModel = None,
                 reranker: Optional[ReRanker] = None,
                 singleton: bool = True
                 ):
        if not hasattr(self, 'initialized'):
            self.embedding_model = embedding_model
            self.reranker = reranker
            self.index = None
            self.documents = []
            self.initialized = True

    def initialize_index(self, dim: int = 1024):
        """显式初始化索引，防止空指针异常"""
        if self.index is None:
            self.index = faiss.IndexFlatL2(dim)
            print(f"已初始化FAISS索引，维度: {dim}")

    def add_documents(self, documents: List[str]):
        if not documents:
            return

        # 生成嵌入
        embeddings = self.embedding_model.embed(documents)
        if not embeddings or len(embeddings) == 0:
            raise ValueError("嵌入模型返回空值")

        # 转换并检查维度
        embeddings = np.array(embeddings, dtype=np.float32)
        if len(embeddings.shape) != 2:
            raise ValueError(f"无效的嵌入维度: {embeddings.shape}")

        # 初始化或检查索引维度
        if self.index is None:
            dim = embeddings.shape[1]
            self.index = faiss.IndexFlatL2(dim)
            print(f"初始化FAISS索引，维度: {dim}")
        elif embeddings.shape[1] != self.index.d:
            raise ValueError(f"嵌入维度不匹配: 期望{self.index.d}，实际{embeddings.shape[1]}")

        # 添加文档到索引
        self.index.add(embeddings)
        self.documents.extend(documents)

    def query(self, query: str, top_k: int = 5, rerank: bool = False) -> List[str]:
        # 添加空库保护
        if not self.documents:
            return []

        # 确保索引已初始化（新增维度校验）
        if self.index is None:
            sample_embed = self.embedding_model.embed(["sample text"])[0]
            self.initialize_index(len(sample_embed))

        try:
            # 生成查询嵌入
            query_embedding = self.embedding_model.embed([query])[0]
            query_embedding = np.array([query_embedding], dtype=np.float32)

            # 动态调整搜索数量（新增安全机制）
            actual_top_k = min(top_k * 2 if rerank else top_k, len(self.documents))

            # 执行搜索（添加异常捕获）
            distances, indices = self.index.search(query_embedding, actual_top_k)

            # 安全过滤无效索引（关键修复）
            valid_indices = [i for i in indices[0] if 0 <= i < len(self.documents)]
            candidate_docs = [self.documents[i] for i in valid_indices]

            # 重排逻辑保持不变...
            return candidate_docs[:top_k]

        except Exception as e:
            print(f"RAG查询失败: {str(e)}")
            return []
