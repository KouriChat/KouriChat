import re
import sys
import time

import numpy as np
import faiss
from abc import ABC, abstractmethod
from typing import List, Optional
import openai
from openai import OpenAI
from sentence_transformers import SentenceTransformer, CrossEncoder
import logging

# 添加颜色常量
YELLOW = "\033[33m"
RESET = "\033[0m"

# 设置日志
logger = logging.getLogger('main')

"""
本文件依赖安装
pip install sentence-transformers faiss-cpu numpy openai
如果使用在线模型需要额外安装openai等对应SDK
"""

# 尝试导入 GPU 版本的 Faiss，如果失败则使用 CPU 版本
try:
    # 仅尝试导入，不实际使用，避免 "name 'GpuIndexIVFFlat' is not defined" 错误
    import faiss
    # 尝试访问GPU模块，而不是直接导入
    if hasattr(faiss, 'contrib') and hasattr(faiss.contrib, 'gpu'):
        logger.info("成功导入 Faiss GPU 支持")
        HAS_GPU = True
    else:
        logger.warning("当前FAISS版本不支持GPU，将使用CPU版本")
        HAS_GPU = False
except (ImportError, AttributeError) as e:
    logger.warning(f"无法导入 Faiss: {str(e)}，将使用 CPU 版本")
    HAS_GPU = False


class EmbeddingModel(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        pass


class LocalEmbeddingModel(EmbeddingModel):
    def __init__(self, model_path: str):
        self.model = SentenceTransformer(model_path)

    def embed(self, texts: List[str]) -> List[List[float]]:
        # 添加进度显示
        total = len(texts)
        logger.info(f"正在生成本地嵌入向量... 0/{total}")
        embeddings = []
        
        for i, text in enumerate(texts):
            embedding = self.model.encode([text], convert_to_tensor=False).tolist()[0]
            embeddings.append(embedding)
            # 更新进度
            if (i+1) % 10 == 0 or i+1 == total:  # 每10个或最后一个更新一次
                logger.info(f"正在生成本地嵌入向量... {i+1}/{total}")
            
        logger.info(f"本地嵌入向量生成完成! 共处理 {total} 条文本")
        return embeddings


class OnlineEmbeddingModel(EmbeddingModel):
    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):  # 参数名与调用处统一
        self.model_name = model_name or "text-embedding-ada-002"  # 使用默认模型
        self.api_key = api_key
        self.base_url = base_url  # 参数名改为base_url
        
        # 创建客户端时处理空值情况
        client_kwargs = {}
        if self.api_key:  # 只有当api_key不为None且不为空字符串时才添加
            client_kwargs["api_key"] = self.api_key
        if self.base_url:  # 只有当base_url不为None且不为空字符串时才添加
            client_kwargs["base_url"] = self.base_url
            
        # 创建OpenAI客户端
        self.client = OpenAI(**client_kwargs)
        
        # 记录初始化信息
        if not self.api_key:
            logger.warning("未提供API密钥，将使用环境变量中的默认值")
        if not self.base_url:
            logger.info("未提供基础URL，将使用OpenAI默认API地址")

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings = []
        total = len(texts)
        success_count = 0
        retry_count = 0
        
        # 计算27%对应的数量
        progress_step = max(1, int(total * 0.27))
        next_progress = progress_step
        
        # 初始化进度显示
        logger.info(f"正在生成在线嵌入向量... 0%")
        
        for i, text in enumerate(texts):
            if not text.strip():
                embeddings.append([])
                success_count += 1
                # 检查是否达到下一个进度点
                if (i + 1) >= next_progress:
                    progress_percent = min(100, int((i + 1) / total * 100))
                    logger.info(f"正在生成在线嵌入向量... {progress_percent}% (成功: {success_count}, 重试: {retry_count})")
                    next_progress += progress_step
                continue

            for attempt in range(1):  # 最多重试1次
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
                    success_count += 1
                    
                    # 检查是否达到下一个进度点
                    if (i + 1) >= next_progress:
                        progress_percent = min(100, int((i + 1) / total * 100))
                        logger.info(f"正在生成在线嵌入向量... {progress_percent}% (成功: {success_count}, 重试: {retry_count})")
                        next_progress += progress_step
                    break
                except Exception as e:
                    retry_count += 1
                    if attempt == 2:
                        logger.warning(f"嵌入失败（文本 {i+1}/{total}）: {str(e)}")
                        embeddings.append([0.0] * 1024)  # 返回默认维度向量
                        # 检查是否达到下一个进度点
                        if (i + 1) >= next_progress:
                            progress_percent = min(100, int((i + 1) / total * 100))
                            logger.info(f"正在生成在线嵌入向量... {progress_percent}% (成功: {success_count}, 重试: {retry_count})")
                            next_progress += progress_step
                    time.sleep(1)  # 重试间隔
        
        # 完成后显示最终结果
        logger.info(f"在线嵌入向量生成完成! 共处理 {total} 条文本 (成功: {success_count}, 重试: {retry_count})")
        return embeddings


class ReRanker(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        pass


class CrossEncoderReRanker(ReRanker):
    def __init__(self, model_path: str):
        self.model = CrossEncoder(model_path)

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        # 添加进度显示
        total = len(documents)
        logger.info(f"正在重排文档... 0/{total}")
        
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs).tolist()
        
        logger.info(f"文档重排完成! 共处理 {total} 条文档")
        return scores


class OnlineCrossEncoderReRanker(ReRanker):
    def __init__(self, model_name: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model_name = model_name or "gpt-3.5-turbo"  # 使用默认模型
        
        # 创建客户端时处理空值情况
        client_kwargs = {}
        if api_key:  # 只有当api_key不为None且不为空字符串时才添加
            client_kwargs["api_key"] = api_key
        if base_url:  # 只有当base_url不为None且不为空字符串时才添加
            client_kwargs["base_url"] = base_url
            
        # 创建OpenAI客户端
        self.client = OpenAI(**client_kwargs)
        
        # 记录初始化信息
        if not api_key:
            logger.warning("未提供API密钥，将使用环境变量中的默认值")
        if not base_url:
            logger.info("未提供基础URL，将使用OpenAI默认API地址")

    def rerank(self, query: str, documents: List[str]) -> List[float]:
        scores = []
        total = len(documents)
        success_count = 0
        error_count = 0
        
        # 初始化进度显示
        logger.info(f"正在进行在线文档重排... 0/{total} (成功: 0, 错误: 0)")
        
        for i, doc in enumerate(documents):
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
                    success_count += 1
                else:
                    score = 0.0  # 解析失败默认值
                    error_count += 1
            except Exception as e:
                score = 0.0  # 异常处理
                error_count += 1
                logger.error(f"重排文档失败: {str(e)}")
                
            scores.append(score)
            # 更新进度显示
            logger.info(f"正在进行在线文档重排... {i+1}/{total} (成功: {success_count}, 错误: {error_count})")
            
        # 完成后清除进度行并显示最终结果
        logger.info(f"在线文档重排完成! 共处理 {total} 条文档 (成功: {success_count}, 错误: {error_count})")
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
            try:
                # 检查是否有 GPU 支持
                if HAS_GPU:
                    try:
                        # 尝试使用 GPU 资源
                        res = faiss.StandardGpuResources()
                        self.index = faiss.GpuIndexFlatL2(res, dim)
                        logger.info(f"已初始化 GPU Faiss 索引，维度: {dim}")
                    except Exception as e:
                        # 如果 GPU 初始化失败，回退到 CPU 版本
                        logger.warning(f"GPU Faiss 索引初始化失败: {str(e)}，回退到 CPU 版本")
                        self.index = faiss.IndexFlatL2(dim)
                        logger.info(f"已初始化 CPU Faiss 索引，维度: {dim}")
                else:
                    # 直接使用 CPU 版本
                    self.index = faiss.IndexFlatL2(dim)
                    logger.info(f"已初始化 CPU Faiss 索引，维度: {dim}")
            except Exception as e:
                # 捕获所有异常，确保索引能够被创建
                logger.error(f"Faiss 索引初始化失败: {str(e)}，使用基础 CPU 索引")
                self.index = faiss.IndexFlatL2(dim)

    def add_documents(self, documents: List[str]):
        if not documents:
            return
            
        logger.info(f"开始处理 {len(documents)} 条文档...")

        # 生成嵌入
        logger.info("正在生成文档嵌入向量...")
        try:
            embeddings = self.embedding_model.embed(documents)
            if not embeddings or len(embeddings) == 0:
                logger.error("嵌入模型返回空值")
                return
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {str(e)}")
            return

        # 转换并检查维度
        logger.info("正在处理嵌入向量...")
        try:
            embeddings = np.array(embeddings, dtype=np.float32)
            if len(embeddings.shape) != 2:
                logger.error(f"无效的嵌入维度: {embeddings.shape}")
                return
        except Exception as e:
            logger.error(f"处理嵌入向量失败: {str(e)}")
            return

        # 初始化或检查索引维度
        if self.index is None:
            dim = embeddings.shape[1]
            try:
                self.initialize_index(dim)
            except Exception as e:
                logger.error(f"初始化索引失败: {str(e)}")
                return
        elif embeddings.shape[1] != self.index.d:
            logger.error(f"嵌入维度不匹配: 期望{self.index.d}，实际{embeddings.shape[1]}")
            return

        # 添加文档到索引
        logger.info("正在将文档添加到索引...")
        try:
            self.index.add(embeddings)
            original_count = len(self.documents)
            self.documents.extend(documents)
            logger.info(f"文档处理完成! 索引中的文档数量: {original_count} -> {len(self.documents)}")
        except Exception as e:
            logger.error(f"添加文档到索引失败: {str(e)}")

    def query(self, query: str, top_k: int = 5, rerank: bool = False) -> List[str]:
        # 添加空库保护
        if not self.documents:
            logger.warning("警告: 文档库为空，无法执行查询")
            return []

        # 确保索引已初始化（新增维度校验）
        if self.index is None:
            logger.info("索引未初始化，正在创建临时索引...")
            try:
                sample_embed = self.embedding_model.embed(["sample text"])[0]
                self.initialize_index(len(sample_embed))
            except Exception as e:
                logger.error(f"初始化索引失败: {str(e)}")
                return []

        try:
            # 生成查询嵌入
            logger.info("正在生成查询嵌入向量...")
            query_embedding = self.embedding_model.embed([query])[0]
            query_embedding = np.array([query_embedding], dtype=np.float32)

            # 动态调整搜索数量（新增安全机制）
            actual_top_k = min(top_k * 2 if rerank else top_k, len(self.documents))
            logger.info(f"正在搜索相关文档 (top_k={actual_top_k})...")

            # 执行搜索（添加异常捕获）
            try:
                distances, indices = self.index.search(query_embedding, actual_top_k)
            except RuntimeError as e:
                if "GPU" in str(e):
                    logger.warning(f"GPU 搜索失败，尝试使用 CPU: {str(e)}")
                    # 创建临时 CPU 索引并复制数据
                    cpu_index = faiss.IndexFlatL2(self.index.d)
                    if hasattr(self.index, 'copyTo'):
                        self.index.copyTo(cpu_index)
                    else:
                        # 如果无法直接复制，尝试重新添加所有向量
                        logger.warning("无法直接复制索引，尝试重建索引...")
                        # 这里假设我们可以从文档重新生成嵌入
                        # 实际应用中可能需要保存原始嵌入或其他恢复机制
                        return []
                    
                    # 使用 CPU 索引搜索
                    distances, indices = cpu_index.search(query_embedding, actual_top_k)
                else:
                    raise

            # 安全过滤无效索引（关键修复）
            valid_indices = [i for i in indices[0] if 0 <= i < len(self.documents)]
            candidate_docs = [self.documents[i] for i in valid_indices]
            
            logger.info(f"找到 {len(candidate_docs)} 个相关文档")
            
            # 如果需要重排序
            if rerank and self.reranker and len(candidate_docs) > 1:
                logger.info("正在对文档进行重排序...")
                scores = self.reranker.rerank(query, candidate_docs)
                # 根据分数排序
                sorted_results = sorted(zip(candidate_docs, scores), key=lambda x: x[1], reverse=True)
                candidate_docs = [doc for doc, _ in sorted_results]
                logger.info(f"文档重排序完成")
            
            result_docs = candidate_docs[:top_k]
            logger.info(f"查询完成，返回 {len(result_docs)} 个结果")
            return result_docs

        except Exception as e:
            logger.error(f"RAG查询失败: {str(e)}")
            return []
