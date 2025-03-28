"""
RAG核心模块 - 提供记忆检索增强生成功能
实现与嵌入、检索、重排序相关的底层功能
"""
import os
import yaml
import json
import logging
import asyncio
import time
import numpy as np
import math
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from datetime import datetime
import re
from src.config import config as rag_config

# 设置日志
logger = logging.getLogger('main')

# 尝试导入APIWrapper
try:
    from src.api_client.wrapper import APIWrapper
except ImportError:
    logger.error("无法导入APIWrapper，嵌入功能将不可用")
    
    # 定义一个空的APIWrapper类，避免未定义错误
    class APIWrapper:
        def __init__(self, api_key=None, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            logger.warning("使用了空的APIWrapper类，实际功能将不可用")

class RagManager:
    """
    RAG管理器 - 管理检索增强生成相关功能
    """
    
    def __init__(self, config_path: str, api_wrapper = None, storage_dir = None):
        """
        初始化RAG管理器
        
        Args:
            config_path: 配置文件路径
            api_wrapper: API调用包装器
            storage_dir: 存储目录，如果提供则覆盖默认存储路径
        """
        self.config_path = config_path
        self.api_wrapper = api_wrapper
        self.storage_dir = storage_dir
        
        # 加载配置
        self.config = self._load_config()
        
        # 获取当前角色名
        try:
            from src.config import config
            self.avatar_name = config.behavior.context.avatar_dir
        except Exception as e:
            logger.error(f"获取角色名失败: {str(e)}")
            self.avatar_name = "default"
        
        # 初始化组件
        self.embedding_model = self._init_embedding_model()
        self.storage = self._init_storage()
        self.reranker = self._init_reranker() if self.config.get("is_rerank", False) else None
        
        # 记录状态
        self.document_count = 0
        
        # 添加向量维度缓存，避免重复警告和计算
        self.standard_vector_dim = None
        self._detect_standard_vector_dimension()
        
        # 设置是否启用混合搜索作为备选
        self.enable_hybrid_fallback = True
        
        logger.info(f"RAG管理器初始化完成，角色: {self.avatar_name}，使用嵌入模型: {self.config.get('embedding_model', {}).get('name', 'default')}，标准向量维度: {self.standard_vector_dim}")
        
    def _load_config(self) -> Dict:
        """
        加载配置文件
        
        Returns:
            Dict: 配置字典
        """
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                return self._create_default_config()
                
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                
            logger.info(f"已加载RAG配置: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}，使用默认配置")
            return self._create_default_config()
            
    def _create_default_config(self) -> Dict:
        """
        创建默认配置
        
        Returns:
            Dict: 默认配置字典
        """
        # 使用rag_config中的配置作为默认值，避免硬编码
        default_config = {
            "api_key": rag_config.OPENAI_API_KEY,
            "base_url": rag_config.OPENAI_API_BASE,
            "embedding_model": {
                "type": "openai",
                "name": rag_config.EMBEDDING_MODEL,
                "dimensions": 1536
            },
            "storage": {
                "type": "json",
                "path": "./data/rag_storage.json"
            },
            "top_k": rag_config.RAG_TOP_K,
            "is_rerank": rag_config.RAG_IS_RERANK,
            "reranker": {
                "type": "api",
                "name": rag_config.RAG_RERANKER_MODEL or "rerank-large"
            },
            "local_model": {
                "enabled": rag_config.LOCAL_MODEL_ENABLED,
                "path": rag_config.LOCAL_EMBEDDING_MODEL_PATH
            }
        }
        
        return default_config
        
    def _init_embedding_model(self):
        """
        初始化嵌入模型
        
        Returns:
            嵌入模型实例
        """
        # 先尝试从配置文件读取嵌入模型名称
        embedding_model_name = None
        try:
            from src.config import config
            
            # 直接从config.rag获取嵌入模型名称
            if hasattr(config, 'rag') and hasattr(config.rag, 'embedding_model'):
                embedding_model_name = config.rag.embedding_model
                logger.info(f"从rag配置中读取到嵌入模型名称: {embedding_model_name}")
                
                # 更新配置
                if embedding_model_name:
                    # 确保self.config中存在embedding_model键，并且是字典类型
                    if "embedding_model" not in self.config:
                        self.config["embedding_model"] = {}
                    
                    # 确保embedding_model是字典类型
                    if not isinstance(self.config["embedding_model"], dict):
                        self.config["embedding_model"] = {"name": embedding_model_name, "type": "openai", "dimensions": 1536}
                    else:
                        self.config["embedding_model"]["name"] = embedding_model_name
                    
                    logger.info(f"将使用从配置文件读取的嵌入模型: {embedding_model_name}")
            else:
                logger.warning("配置对象中不存在rag.embedding_model属性")
                
        except Exception as e:
            logger.error(f"读取嵌入模型配置失败: {str(e)}")
        
        # 如果没有读取到有效的模型名称，使用默认值
        if not embedding_model_name:
            logger.info("未从配置文件读取到有效的嵌入模型名称，使用默认值")
        
        # 从配置中获取模型信息
        model_config = self.config.get("embedding_model", {})
        model_type = model_config.get("type", "openai")
        model_name = model_config.get("name", "text-embedding-3-large")
        
        # 记录最终使用的模型名称
        logger.info(f"RAG系统最终使用的嵌入模型名称: {model_name}")
        
        # 检查是否启用本地模型
        local_model_config = self.config.get("local_model", {})
        use_local_model = local_model_config.get("enabled", False)
        local_model_path = local_model_config.get("path", "")
        
        if use_local_model and os.path.exists(local_model_path):
            try:
                logger.info(f"尝试加载本地嵌入模型: {local_model_path}")
                # 这里可以实现本地模型的加载逻辑
                # 为了降低内存占用，本地模型加载可以懒加载或使用更轻量的实现
                return LocalEmbeddingModel(local_model_path)
            except Exception as e:
                logger.error(f"加载本地嵌入模型失败: {str(e)}，将使用API模型")
        
        # 如果api_wrapper为None，尝试初始化一个
        if self.api_wrapper is None:
            try:
                # 尝试从配置文件获取RAG专用的API密钥和URL
                try:
                    from src.config import config
                    
                    api_key = None
                    base_url = None
                    
                    # 直接从config.rag获取API设置
                    if hasattr(config, 'rag'):
                        api_key = config.rag.api_key
                        base_url = config.rag.base_url
                        
                        if api_key:
                            logger.info("成功从config.rag中读取API设置")
                            self.api_wrapper = APIWrapper(
                                api_key=api_key,
                                base_url=base_url if base_url else None
                            )
                            logger.info("成功创建RAG专用API包装器")
                        else:
                            logger.warning("从config.rag中读取的API密钥为空")
                    else:
                        logger.warning("配置对象中不存在rag属性")
                        
                except Exception as config_error:
                    logger.error(f"从配置文件获取RAG API设置失败: {str(config_error)}")
                    
            except Exception as e:
                logger.error(f"初始化API包装器失败: {str(e)}")
        
        # 使用API模型
        logger.info(f"使用API嵌入模型: {model_name}")
        return ApiEmbeddingModel(self.api_wrapper, model_name, model_type)
    
    def _init_storage(self):
        """
        初始化存储系统
        
        Returns:
            存储系统实例
        """
        storage_config = self.config.get("storage", {})
        storage_type = storage_config.get("type", "json")
        
        # 如果提供了storage_dir，使用该目录
        if self.storage_dir:
            # 使用提供的存储目录，文件名固定为rag_storage.json，确保与私聊一致
            storage_filename = "rag_storage.json"
            avatar_storage_path = os.path.join(self.storage_dir, storage_filename)
            
            # 确保路径有效
            os.makedirs(self.storage_dir, exist_ok=True)
            
            logger.info(f"初始化RAG存储: {storage_type}, 使用自定义路径: {avatar_storage_path}")
            return JsonStorage(avatar_storage_path)
        
        # 否则使用角色专属的存储路径，确保与memory.json在同一文件夹
        base_storage_path = storage_config.get("path", "./data/rag_storage.json")
        storage_filename = os.path.basename(base_storage_path)
        
        # 角色记忆目录为 data/avatars/角色名/
        avatar_storage_dir = os.path.join("data", "avatars", self.avatar_name)
        avatar_storage_path = os.path.join(avatar_storage_dir, storage_filename)
        
        # 确保路径有效
        os.makedirs(avatar_storage_dir, exist_ok=True)
        
        logger.info(f"初始化RAG存储: {storage_type}, 路径: {avatar_storage_path}")
        return JsonStorage(avatar_storage_path)
    
    def _init_reranker(self):
        """
        初始化重排序器
        
        Returns:
            重排序器实例
        """
        if not self.config.get("is_rerank", False):
            return None
            
        reranker_config = self.config.get("reranker", {})
        reranker_type = reranker_config.get("type", "api")
        reranker_name = reranker_config.get("name", "rerank-large")
        
        logger.info(f"初始化重排序器: {reranker_type}, 模型: {reranker_name}")
        
        # 使用API重排序器
        return ApiReranker(self.api_wrapper, reranker_name)
    
    def _ensure_valid_path(self, path: str) -> str:
        """
        确保路径有效（处理相对路径等）
        
        Args:
            path: 原始路径
            
        Returns:
            str: 有效的绝对路径
        """
        # 如果是相对路径，转换为绝对路径
        if not os.path.isabs(path):
            # 相对于配置文件的路径
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            abs_path = os.path.join(config_dir, path)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            
            return abs_path
        
        # 确保目录存在
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        return path
    
    def _detect_standard_vector_dimension(self):
        """检测并设置标准向量维度"""
        try:
            # 首先尝试从配置中获取
            model_config = self.config.get("embedding_model", {})
            configured_dim = model_config.get("dimensions")
            
            if configured_dim and isinstance(configured_dim, int) and configured_dim > 0:
                self.standard_vector_dim = configured_dim
                logger.debug(f"从配置中获取标准向量维度: {self.standard_vector_dim}")
                return
                
            # 如果配置中没有，则从现有文档中检测
            if hasattr(self, 'storage') and self.storage:
                documents = self.storage.data.get("documents", [])
                for doc in documents:
                    embedding = doc.get("embedding")
                    if embedding and isinstance(embedding, list) and len(embedding) > 0:
                        self.standard_vector_dim = len(embedding)
                        logger.debug(f"从现有文档中检测到标准向量维度: {self.standard_vector_dim}")
                        return
            
            # 如果没有现有文档，设置默认值
            # 优先使用3072（text-embedding-3-large）或1536（text-embedding-3-small）
            model_name = model_config.get("name", "").lower()
            if "text-embedding-3-large" in model_name:
                self.standard_vector_dim = 3072
            elif "text-embedding-3-small" in model_name:
                self.standard_vector_dim = 1536
            else:
                # 默认使用1536维，这是OpenAI的旧模型维度
                self.standard_vector_dim = 1536
                
            logger.debug(f"设置默认标准向量维度: {self.standard_vector_dim}")
            
        except Exception as e:
            logger.error(f"检测标准向量维度失败: {str(e)}, 使用默认维度 1536")
            self.standard_vector_dim = 1536

    async def add_document(self, document: Dict, user_id: str = None) -> bool:
        """
        添加文档到RAG系统
        
        Args:
            document: 文档字典，包含id、content和metadata
            user_id: 用户ID，用于标识文档所属用户
            
        Returns:
            bool: 是否成功添加
        """
        try:
            # 检查文档格式
            if not self._validate_document(document):
                logger.warning(f"文档格式无效: {document}")
                return False
                
            # 生成嵌入向量
            content = document.get("content", "")
            embedding = await self.embedding_model.get_embedding(content)
            
            if embedding is None:
                logger.warning("生成嵌入向量失败，跳过添加文档")
                return False
                
            # 添加嵌入向量到文档，并确保维度一致
            standardized_embedding = self._standardize_vector_dimension(embedding)
            document["embedding"] = standardized_embedding
            
            # 如果这是第一个文档，更新标准向量维度
            if self.standard_vector_dim is None:
                self.standard_vector_dim = len(standardized_embedding)
                logger.debug(f"设置标准向量维度为: {self.standard_vector_dim}")
            
            # 添加用户ID到元数据
            if user_id:
                if "metadata" not in document:
                    document["metadata"] = {}
                document["metadata"]["user_id"] = user_id
            
            # 保存到存储
            success = self.storage.add_document(document)
            
            if success:
                self.document_count = self.storage.get_document_count()
                logger.info(f"成功添加文档到RAG系统，当前文档数: {self.document_count}")
            
            return success
        except Exception as e:
            logger.error(f"添加文档失败: {str(e)}")
            return False
    
    def _standardize_vector_dimension(self, vector):
        """统一向量维度到标准尺寸"""
        if not isinstance(vector, list) and not (hasattr(vector, 'shape') and hasattr(vector, 'tolist')):
            # 如果不是列表或numpy数组，尝试转换
            try:
                vector = list(vector)
            except:
                logger.error(f"无法转换向量类型: {type(vector)}")
                return vector
        
        # 确保是列表
        if hasattr(vector, 'tolist'):
            vector = vector.tolist()
            
        # 如果没有设置标准维度，以当前向量维度为准
        if self.standard_vector_dim is None:
            self.standard_vector_dim = len(vector)
            logger.debug(f"设置标准向量维度为: {self.standard_vector_dim}")
            return vector
            
        current_dim = len(vector)
        
        # 如果维度已经匹配，直接返回
        if current_dim == self.standard_vector_dim:
            return vector
            
        # 调整维度
        if current_dim < self.standard_vector_dim:
            # 填充零
            padding = [0.0] * (self.standard_vector_dim - current_dim)
            logger.debug(f"向量维度不足，从{current_dim}填充至{self.standard_vector_dim}维")
            return vector + padding
        else:
            # 截断
            logger.debug(f"向量维度过大，从{current_dim}截断至{self.standard_vector_dim}维")
            return vector[:self.standard_vector_dim]
            
    async def update_document(self, document: Dict) -> bool:
        """
        更新RAG系统中的文档
        
        Args:
            document: 文档字典，包含id、content和metadata
            
        Returns:
            bool: 是否成功更新
        """
        try:
            # 检查文档格式
            if not self._validate_document(document):
                logger.warning(f"文档格式无效: {document}")
                return False
                
            # 检查是否需要更新嵌入向量
            if "embedding" not in document:
                # 生成嵌入向量
                content = document.get("content", "")
                embedding = await self.embedding_model.get_embedding(content)
                
                if embedding is None:
                    logger.warning("生成嵌入向量失败，跳过更新文档")
                    return False
                    
                # 添加嵌入向量到文档
                document["embedding"] = embedding
            
            # 保存到存储
            # 这里假设storage有update_document方法，如果没有需要实现
            if hasattr(self.storage, 'update_document'):
                success = self.storage.update_document(document)
            else:
                # 如果storage没有update_document方法，使用add_document替代
                # 这依赖于storage的add_document实现，它应该能处理现有文档的更新
                success = self.storage.add_document(document)
            
            if success:
                logger.info(f"成功更新文档")
            
            return success
        except Exception as e:
            logger.error(f"更新文档失败: {str(e)}")
            return False
            
    def _validate_document(self, document: Dict) -> bool:
        """
        验证文档格式
        
        Args:
            document: 待验证的文档
            
        Returns:
            bool: 文档是否有效
        """
        # 检查必要字段
        if not document.get("id") or not document.get("content"):
            return False
            
        # 检查内容长度
        content = document.get("content", "")
        if len(content) < 10:  # 过短的内容可能没有价值
            return False
            
        return True
    
    async def query(self, query_text: str, top_k: int = None) -> List[Dict]:
        """
        查询相关文档
        
        Args:
            query_text: 查询文本
            top_k: 返回结果数量，如果为None则使用配置中的值
            
        Returns:
            List[Dict]: 相关文档列表
        """
        try:
            # 使用配置的top_k值（如果未指定）
            if top_k is None:
                top_k = self.config.get("top_k", 5)
                
            # 生成查询嵌入向量
            query_embedding = await self.embedding_model.get_embedding(query_text)
            
            if query_embedding is None:
                logger.warning("生成查询嵌入向量失败，尝试使用混合特征备选方法")
                if self.enable_hybrid_fallback:
                    return self.hybrid_feature_search(query_text, top_k)
                return []
                
            # 标准化查询向量维度
            query_embedding = self._standardize_vector_dimension(query_embedding)
                
            # 从存储中检索相关文档，使用角色名作为过滤条件
            # 这确保只检索当前角色的记忆
            results = self.storage.search(
                query_embedding, 
                top_k * 2,  # 检索更多结果以便重排序
                avatar_name=self.avatar_name  # 使用当前角色名作为过滤条件
            )
            
            if not results:
                logger.info("向量搜索未找到相关文档，尝试使用混合特征备选方法")
                if self.enable_hybrid_fallback:
                    return self.hybrid_feature_search(query_text, top_k)
                return []
                
            # 如果启用了重排序，对结果进行重排序
            if self.reranker and len(results) > 1:
                reranked_results = await self.reranker.rerank(query_text, results)
                results = reranked_results[:top_k]  # 截取top_k个结果
            else:
                results = results[:top_k]  # 直接截取top_k个结果
                
            logger.info(f"查询成功，找到 {len(results)} 个相关文档，角色: {self.avatar_name}")
            return results
        except Exception as e:
            logger.error(f"向量查询失败: {str(e)}，尝试使用混合特征备选方法")
            if self.enable_hybrid_fallback:
                return self.hybrid_feature_search(query_text, top_k)
            return []
    
    def hybrid_feature_search(self, query_text: str, top_k: int = 5) -> List[Dict]:
        """
        使用混合特征搜索，包括TF-IDF特征和嵌入特征
        
        Args:
            query_text: 查询文本
            top_k: 返回结果数量
            
        Returns:
            List[Dict]: 相关文档列表
        """
        try:
            logger.info(f"开始混合特征搜索: {query_text[:30]}...")
            
            # 获取所有文档
            all_documents = self.storage.data.get("documents", [])
            
            # 过滤出当前角色的文档
            documents = []
            for doc in all_documents:
                metadata = doc.get("metadata", {})
                doc_user_id = metadata.get("user_id", "")
                # 检查文档是否属于当前角色（支持多种可能的元数据字段）
                if (doc_user_id == self.avatar_name or 
                    metadata.get("ai_name") == self.avatar_name or
                    metadata.get("avatar_name") == self.avatar_name):
                    documents.append(doc)
            
            if not documents:
                logger.warning(f"未找到角色 {self.avatar_name} 的文档")
                return []
            
            # 导入所需库
            import jieba
            from difflib import SequenceMatcher
            from datetime import datetime
            import math
            import re
            
            # 当前时间
            current_time = datetime.now()
            
            # 最新消息的轮数（用于计算轮数差）
            latest_turn = 0
            for doc in documents:
                metadata = doc.get("metadata", {})
                turn = metadata.get("turn", 0)
                if turn > latest_turn:
                    latest_turn = turn
            
            # 对查询文本进行分词
            query_words = set(jieba.cut(query_text))
            
            # 计算每个文档的混合特征分数
            scored_docs = []
            for doc in documents:
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                
                # 1. 时间衰减 (40%)
                time_weight = 0.5  # 默认中等权重
                timestamp = metadata.get("timestamp", "")
                if timestamp:
                    time_weight = self._calculate_time_decay_weight(timestamp, current_time)
                
                # 2. 对话轮数之差 (25%)
                turn_weight = 0.5  # 默认中等权重
                turn = metadata.get("turn", 0)
                if latest_turn > 0:
                    # 轮数差越小，权重越高
                    turn_diff = latest_turn - turn
                    # 指数衰减：最近的轮次接近1，远的轮次接近0
                    turn_weight = math.exp(-0.1 * turn_diff)
                    turn_weight = max(0.1, min(1.0, turn_weight))
                
                # 3. 匹配程度 (15%)
                match_weight = 0.1  # 默认低权重
                
                # 3.1 关键词匹配
                doc_words = set(jieba.cut(content))
                keyword_matches = query_words.intersection(doc_words)
                keyword_score = len(keyword_matches) / max(len(query_words), 1)
                
                # 3.2 序列匹配
                sequence_score = SequenceMatcher(None, query_text, content).ratio()
                
                # 3.3 正则表达式匹配关键概念
                # 提取查询中的实体、日期、时间、数字等
                entities = re.findall(r'[\u4e00-\u9fa5]{2,}|[A-Za-z]{2,}|\d{2,}', query_text)
                entity_matches = 0
                for entity in entities:
                    if entity in content:
                        entity_matches += 1
                entity_score = entity_matches / max(len(entities), 1)
                
                # 组合不同的匹配分数
                match_weight = 0.4 * keyword_score + 0.3 * sequence_score + 0.3 * entity_score
                match_weight = max(0.1, min(1.0, match_weight))
                
                # 4. 内容质量 (20%)
                quality_weight = 0.5  # 默认中等质量
                
                # 4.1 长度评分（假设长度适中的内容质量更高）
                content_length = len(content)
                length_score = 0
                if content_length < 10:
                    length_score = 0.2  # 太短
                elif content_length < 50:
                    length_score = 0.5  # 较短
                elif content_length < 200:
                    length_score = 1.0  # 适中
                elif content_length < 500:
                    length_score = 0.8  # 较长
                else:
                    length_score = 0.6  # 太长
                
                # 4.2 信息密度（关键词密度）
                keywords = ["什么", "为什么", "怎么", "何时", "何地", "谁", "哪里"]
                keyword_density = sum(1 for word in keywords if word in content) / max(len(content) / 10, 1)
                density_score = min(1.0, keyword_density * 2)
                
                # 4.3 特殊属性评分
                special_score = 0.5
                # 包含问答对，质量可能更高
                if "?" in content or "？" in content:
                    special_score += 0.3
                # 包含引号，可能是引用内容，质量更高
                if "\"" in content or "\"" in content or "'" in content:
                    special_score += 0.2
                special_score = min(1.0, special_score)
                
                # 组合不同的质量分数
                quality_weight = 0.4 * length_score + 0.3 * density_score + 0.3 * special_score
                quality_weight = max(0.1, min(1.0, quality_weight))
                
                # 最终混合分数（按权重组合）
                final_score = (
                    0.4 * time_weight +       # 时间衰减 (40%)
                    0.25 * turn_weight +      # 对话轮数之差 (25%)
                    0.15 * match_weight +     # 匹配程度 (15%)
                    0.2 * quality_weight      # 内容质量 (20%)
                )
                
                # 存储计算结果
                scored_docs.append({
                    "id": doc.get("id"),
                    "content": content,
                    "metadata": metadata,
                    "score": final_score,
                    "_debug": {
                        "time_weight": time_weight,
                        "turn_weight": turn_weight,
                        "match_weight": match_weight,
                        "quality_weight": quality_weight
                    }
                })
            
            # 按分数排序
            scored_docs.sort(key=lambda x: x["score"], reverse=True)
            
            # 截取top_k个结果
            results = scored_docs[:top_k]
            
            # 移除调试信息
            for doc in results:
                if "_debug" in doc:
                    del doc["_debug"]
            
            logger.info(f"混合特征搜索完成，找到 {len(results)} 个相关文档")
            return results
        except Exception as e:
            logger.error(f"混合特征搜索失败: {str(e)}")
            return []
    
    async def is_important(self, text: str) -> bool:
        """判断文本是否包含重要信息:
        
        Args:
            text: 待判断的文本
            
        Returns:
            bool: 是否包含重要信息
        """
        try:
            # 先使用规则判断
            if self._rule_based_importance(text):
                return True
            
            # 如果有API，使用LLM判断
            if self.api_wrapper:
                try:
                    prompt = "请分析以下文本是否包含重要信息。\n\n文本：{text}\n\n请直接回答是或否。"
                    response = await self.api_wrapper.async_completion(
                        prompt=prompt,
                        temperature=0.1,
                        max_tokens=10
                    )
                    
                    response_text = response.get("content", "").strip().lower()
                    return "是" in response_text or "yes" in response_text
                except Exception as e:
                    logger.error(f"使用LLM判断重要性失败: {str(e)}")
            
            # 默认返回基于规则的判断
            return self._rule_based_importance(text)
        except Exception as e:
            logger.error(f"判断文本重要性失败: {str(e)}")
            return False
    
    def _rule_based_importance(self, text: str) -> bool:
        """
        基于规则判断文本重要性
        
        Args:
            text: 待判断的文本
            
        Returns:
            bool: 是否包含重要信息
        """
        try:
            # 1. 长度判断
            if len(text) > 100:  # 长文本更可能包含重要信息
                return True
            
            # 2. 关键词判断
            important_keywords = [
                "记住", "牢记", "不要忘记", "重要", "必须", "一定要",
                "地址", "电话", "密码", "账号", "名字", "生日",
                "喜欢", "讨厌", "爱好", "兴趣"
            ]
            
            for keyword in important_keywords:
                if keyword in text:
                    return True
            
            # 3. 包含数字、日期等特定格式
            if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', text):  # 日期格式
                return True
            
            if re.search(r'\d{3,}', text):  # 至少3位数的数字
                return True
            
            return False
        except Exception as e:
            logger.error(f"规则判断失败: {str(e)}")
            return False
    
    async def generate_summary(self, user_id: str = None, limit: int = 20) -> str:
        """
        生成记忆摘要
        
        Args:
            user_id: 用户ID，如果提供则只总结该用户的记忆
            limit: 摘要包含的记忆条数
            
        Returns:
            str: 记忆摘要
        """
        try:
            if not self.api_wrapper:
                logger.error("未提供API包装器，无法生成摘要")
                return ""
                
            # 获取最新的记忆
            documents = self.storage.get_latest_documents(limit, user_id)
            
            if not documents:
                return "没有可用的记忆。"
                
            # 格式化记忆
            memory_text = ""
            for i, doc in enumerate(documents):
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                timestamp = metadata.get("timestamp", "未知时间")
                memory_text += f"记忆 {i+1} [{timestamp}]:\n{content}\n\n"
            
            # 构造摘要请求
            prompt = f"""请根据以下对话记忆，总结出重要的信息点：

{memory_text}

请提供一个简洁的摘要，包含关键信息点和重要的细节。"""

            # 调用API生成摘要
            response = await self.api_wrapper.async_completion(
                prompt=prompt,
                temperature=0.3,
                max_tokens=500
            )
            
            return response.get("content", "无法生成摘要")
        except Exception as e:
            logger.error(f"生成记忆摘要失败: {str(e)}")
            return "生成摘要时出错"
            
    def clear_storage(self, user_id: str = None) -> bool:
        """
        清空存储
        
        Args:
            user_id: 用户ID，如果提供则只清空该用户的记忆
            
        Returns:
            bool: 是否成功清空
        """
        try:
            if user_id:
                # 只清空指定角色的记忆
                self.data["documents"] = [doc for doc in self.data.get("documents", [])
                                        if doc.get("metadata", {}).get("user_id") != user_id]
            else:
                # 清空所有记忆
                self.data = {"documents": []}
            
            self._save_data()
            return True
        except Exception as e:
            logger.error(f"清空存储失败: {str(e)}")
            return False

    # 在RagManager类中添加群聊上下文相关方法
    async def group_chat_query(self, group_id: str, current_timestamp: str, context_size: int = 7) -> List[Dict]:
        """
        获取群聊上下文消息，返回最近的N轮对话
        
        Args:
            group_id: 群聊ID
            current_timestamp: 当前消息时间戳，用于排除当前消息
            context_size: 获取的上下文消息数量
            
        Returns:
            List[Dict]: 按时间排序的上下文消息
        """
        try:
            if not hasattr(self.storage, 'data'):
                return []
            
            if 'group_chats' not in self.storage.data:
                return []
            
            if group_id not in self.storage.data['group_chats']:
                return []
            
            # 获取所有群聊消息
            all_messages = self.storage.data['group_chats'][group_id]
            
            # 过滤掉当前消息
            filtered_messages = [
                msg for msg in all_messages
                if msg.get('timestamp') != current_timestamp
            ]
            
            # 按时间戳排序，最新的在前面
            sorted_messages = sorted(
                filtered_messages,
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )
            
            # 返回指定数量的消息（最近的N条）
            recent_messages = sorted_messages[:context_size]
            
            # 再按时间顺序排序，时间早的在前面
            time_ordered_messages = sorted(
                recent_messages,
                key=lambda x: x.get('timestamp', '')
            )
            
            return time_ordered_messages
        
        except Exception as e:
            logger.error(f"获取群聊上下文消息失败: {str(e)}")
            return []
    
    async def add_group_chat_message(self, group_id: str, message: Dict) -> bool:
        """
        添加群聊消息到RAG系统
        
        Args:
            group_id: 群聊ID
            message: 消息字典，包含timestamp、sender_name、human_message等字段
            
        Returns:
            bool: 是否成功添加
        """
        try:
            if not hasattr(self.storage, 'data'):
                self.storage.data = {}
            
            if 'group_chats' not in self.storage.data:
                self.storage.data['group_chats'] = {}
            
            if group_id not in self.storage.data['group_chats']:
                self.storage.data['group_chats'][group_id] = []
            
            # 提取消息信息
            timestamp = message.get('timestamp', '')
            human_message = message.get('human_message', '')
            sender_name = message.get('sender_name', '')
            assistant_message = message.get('assistant_message')
            is_at = message.get('is_at', False)
            ai_name = message.get('ai_name', self.avatar_name)
            
            # 创建RAG存储格式的消息对象 - 确保与rag_storage.json格式一致
            rag_message = {
                "id": f"group_chat_{group_id}_{int(time.time())}" if 'id' not in message else message['id'],
                "content": self._format_content_for_rag(human_message, assistant_message, sender_name),
                "embedding": None,  # 将在后面获取嵌入向量
                "metadata": {
                    "type": "group_chat_message",
                    "group_id": group_id,
                    "timestamp": timestamp,
                    "sender_name": sender_name,
                    "sender_id": sender_name,  # 使用sender_name作为sender_id
                    "is_at": is_at,
                    "ai_name": ai_name,
                    "human_message": human_message,
                    "assistant_message": assistant_message
                }
            }
            
            # 查找是否存在相同时间戳的消息
            existing_messages = [msg for msg in self.storage.data['group_chats'][group_id] 
                                if msg.get('timestamp') == timestamp]
            
            if existing_messages:
                for existing_msg in existing_messages:
                    existing_msg.update(message)
            else:
                self.storage.data['group_chats'][group_id].append(message)
            
            # 保存原始消息格式到group_chats
            self.storage._save_data()
            
            # 构建用于嵌入的内容
            content_for_embedding = self._format_content_for_rag(human_message, assistant_message, sender_name)
            
            # 获取嵌入向量
            embedding = await self.embedding_model.get_embedding(content_for_embedding)
            if embedding:
                rag_message["embedding"] = embedding
                # 使用RAG格式添加文档，确保rag_storage.json中的格式正确
                self.storage.add_document(rag_message)
            
            return True
        except Exception as e:
            logger.error(f"添加群聊消息到RAG系统失败: {str(e)}")
            return False
    
    def _format_content_for_rag(self, human_message, assistant_message, sender_name):
        """格式化RAG内容"""
        content = f"{sender_name}: {human_message}"
        if assistant_message:
            content += f"\n{self.avatar_name}: {assistant_message}"
        return content
    
    async def update_group_chat_response(self, group_id: str, timestamp: str, response: str) -> bool:
        """
        更新群聊助手回复
        
        Args:
            group_id: 群聊ID
            timestamp: 消息时间戳
            response: 助手回复
            
        Returns:
            bool: 是否成功更新
        """
        try:
            if not hasattr(self.storage, 'data') or 'group_chats' not in self.storage.data:
                logger.warning(f"群聊存储未初始化")
                return False
            
            if group_id not in self.storage.data['group_chats']:
                logger.warning(f"群聊 {group_id} 在RAG存储中不存在")
                return False
            
            found = False
            sender_name = ""
            human_message = ""
            
            # 更新memory.json格式的消息
            for message in self.storage.data['group_chats'][group_id]:
                if message.get('timestamp') == timestamp:
                    message['assistant_message'] = response
                    sender_name = message.get('sender_name', '')
                    human_message = message.get('human_message', '')
                    found = True
                    break
            
            if not found:
                logger.warning(f"未找到时间戳为 {timestamp} 的群聊消息")
                return False
            
            self.storage._save_data()
            
            # 更新RAG存储中的文档
            query = f"timestamp:{timestamp} AND group_id:{group_id}"
            results = await self.query(query, top_k=1)
            
            if results:
                doc = results[0]
                doc["metadata"]["assistant_message"] = response
                # 更新内容字段，确保格式一致
                doc["content"] = self._format_content_for_rag(human_message, response, sender_name)
                
                await self.update_document(doc)
            
            return True
        except Exception as e:
            logger.error(f"更新群聊助手回复失败: {str(e)}")
            return False

    def _calculate_time_decay_weight(self, timestamp_str: str, current_time=None) -> float:
        """
        计算基于时间衰减的权重
        
        Args:
            timestamp_str: 时间戳字符串
            current_time: 当前时间，如果为None则使用当前时间
            
        Returns:
            float: 时间衰减权重 (0~1)
        """
        try:
            # 如果时间戳为空，返回默认中等权重
            if not timestamp_str:
                return 0.5
            
            # 初始化当前时间
            if current_time is None:
                current_time = datetime.now()
            elif isinstance(current_time, str):
                try:
                    # 尝试解析字符串时间
                    current_time = datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        current_time = datetime.strptime(current_time, '%Y-%m-%d %H:%M')
                    except ValueError:
                        # 如果都失败，使用当前时间
                        current_time = datetime.now()
                        logger.debug(f"无法解析当前时间字符串: {current_time}，使用系统当前时间")
            
            # 尝试解析时间戳字符串
            timestamp = None
            
            # 定义可能的时间格式列表，按照优先级排序
            formats_to_try = [
                '%Y-%m-%d %H:%M:%S',  # 标准格式（带秒）
                '%Y-%m-%d %H:%M',     # 标准格式（不带秒）
                '%Y/%m/%d %H:%M:%S',  # 斜杠分隔（带秒）
                '%Y/%m/%d %H:%M',     # 斜杠分隔（不带秒）
                '%Y-%m-%dT%H:%M:%S',  # ISO格式（带秒）
                '%Y-%m-%dT%H:%M',     # ISO格式（不带秒）
                '%Y%m%d%H%M%S',       # 紧凑型（带秒）
                '%Y%m%d%H%M'          # 紧凑型（不带秒）
            ]
            
            # 尝试使用每种格式解析时间戳
            for time_format in formats_to_try:
                try:
                    timestamp = datetime.strptime(timestamp_str, time_format)
                    break  # 成功解析，跳出循环
                except ValueError:
                    continue  # 尝试下一种格式
            
            # 如果无法使用预定义格式解析，尝试正则表达式提取日期部分
            if timestamp is None:
                try:
                    # 提取年月日时分秒
                    date_match = re.search(r'(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})[T\s]?(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', timestamp_str)
                    if date_match:
                        year, month, day, hour, minute = map(int, date_match.groups()[:5])
                        second = int(date_match.group(6)) if date_match.group(6) else 0
                        try:
                            timestamp = datetime(year, month, day, hour, minute, second)
                        except ValueError as e:
                            # 处理无效日期/时间值
                            logger.warning(f"从字符串中提取的日期时间值无效: {e}")
                            return 0.5
                    else:
                        # 如果没有匹配到日期时间格式，返回中等权重
                        logger.debug(f"无法识别的时间戳格式: {timestamp_str}")
                        return 0.5
                except Exception as e:
                    logger.warning(f"解析时间戳时出错: {str(e)}")
                    return 0.5
            
            # 如果到这里还是无法解析，返回默认权重
            if timestamp is None:
                logger.debug(f"无法解析时间戳: {timestamp_str}")
                return 0.5
            
            # 计算时间差（小时）
            try:
                time_diff_seconds = (current_time - timestamp).total_seconds()
                # 如果时间差为负数，可能是时区问题或时钟不同步，使用绝对值
                time_diff_seconds = abs(time_diff_seconds)
                time_diff_hours = time_diff_seconds / 3600.0
            except Exception as e:
                logger.warning(f"计算时间差异时出错: {str(e)}")
                return 0.5
            
            # 最大时间差为3天(72小时)
            max_hours = 72.0  # 3天
            time_diff_hours = min(time_diff_hours, max_hours)
            
            # 分段式衰减函数
            # 1. 24小时内: 缓慢衰减
            # 2. 24-72小时: 快速衰减
            # 3. 72小时后: 稳定在略高于最小阈值
            
            min_weight = 0.15  # 最小权重阈值
            
            if time_diff_hours <= 24.0:
                # 24小时内缓慢衰减：从1.0到0.7
                weight = 1.0 - (0.3 * time_diff_hours / 24.0)
            elif time_diff_hours <= max_hours:
                # 24-72小时快速衰减：从0.7到min_weight
                remaining_decay = 0.7 - min_weight
                normalized_time = (time_diff_hours - 24.0) / (max_hours - 24.0)
                weight = 0.7 - (remaining_decay * normalized_time)
            else:
                # 72小时后稳定在最小值
                weight = min_weight
            
            # 限制权重范围在0.1~1.0之间
            weight = max(min_weight, min(1.0, weight))
            
            return weight
            
        except Exception as e:
            logger.error(f"计算时间衰减权重失败: {str(e)}")
            # 返回中等权重作为默认值
            return 0.5

# 嵌入模型实现
class ApiEmbeddingModel:
    """API嵌入模型"""
    
    def __init__(self, api_wrapper, model_name, model_type="openai"):
        """
        初始化API嵌入模型
        
        Args:
            api_wrapper: API调用包装器
            model_name: 模型名称
            model_type: 模型类型
        """
        self.api_wrapper = api_wrapper
        self.model_name = model_name
        self.model_type = model_type
        self.cache = {}  # 简单缓存，避免重复计算
        self.cache_hits = 0
        self.cache_misses = 0
        self.max_cache_size = 1000
        
    async def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 嵌入向量
        """
        # 检查缓存
        if text in self.cache:
            self.cache_hits += 1
            return self.cache[text]
            
        self.cache_misses += 1
        
        try:
            if not self.api_wrapper:
                logger.error("API包装器未初始化，无法获取嵌入向量")
                return None
                
            # 使用API获取嵌入向量
            try:
                # 首先尝试异步方法
                if hasattr(self.api_wrapper, 'async_embedding'):
                    embedding = await self.api_wrapper.async_embedding(text, self.model_name)
                # 如果不存在异步方法，则使用同步方法
                elif hasattr(self.api_wrapper, 'embedding'):
                    embedding = self.api_wrapper.embedding(text, self.model_name)
                else:
                    # 直接调用底层API
                    response = await self.api_wrapper.embeddings.create(
                        model=self.model_name,
                        input=text
                    )
                    if hasattr(response, 'data') and len(response.data) > 0:
                        embedding = response.data[0].embedding
                    elif isinstance(response, dict) and 'data' in response:
                        embedding = response['data'][0]['embedding']
                    else:
                        logger.error(f"无法解析嵌入向量响应: {response}")
                        return None
            except Exception as e:
                logger.error(f"调用嵌入API失败: {str(e)}")
                return None
                
            # 缓存结果
            self.cache[text] = embedding
            
            # 限制缓存大小
            if len(self.cache) > self.max_cache_size:
                # 删除最旧的项
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                
            return embedding
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {str(e)}")
            return None
            
    def get_cache_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 缓存统计信息
        """
        return {
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "size": len(self.cache),
            "max_size": self.max_cache_size
        }

class LocalEmbeddingModel:
    """本地嵌入模型"""
    
    def __init__(self, model_path):
        """
        初始化本地嵌入模型
        
        Args:
            model_path: 模型路径
        """
        self.model_path = model_path
        self.model = None
        self.cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.max_cache_size = 1000
        
        # 懒加载模型，降低内存占用
        
    async def get_embedding(self, text: str) -> List[float]:
        """
        获取文本的嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 嵌入向量
        """
        # 检查缓存
        if text in self.cache:
            self.cache_hits += 1
            return self.cache[text]
            
        self.cache_misses += 1
        
        try:
            # 懒加载模型
            if self.model is None:
                self._load_model()
                
            if self.model is None:
                logger.error("本地模型加载失败，无法获取嵌入向量")
                return None
                
            # 使用本地模型获取嵌入向量
            embedding = self._get_embedding_with_local_model(text)
            
            # 缓存结果
            self.cache[text] = embedding
            
            # 限制缓存大小
            if len(self.cache) > self.max_cache_size:
                # 删除最旧的项
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                
            return embedding
        except Exception as e:
            logger.error(f"获取嵌入向量失败: {str(e)}")
            return None
            
    def _load_model(self):
        """加载本地模型"""
        try:
            # 这里实现本地模型加载逻辑
            # 由于可能占用较多内存，所以采用懒加载方式
            logger.info(f"加载本地嵌入模型: {self.model_path}")
            
            # 示例：加载ONNX模型
            try:
                import onnxruntime as ort  # type: ignore
                self.model = ort.InferenceSession(self.model_path)
                logger.info("成功加载本地嵌入模型")
            except ImportError:
                logger.error("未安装onnxruntime，无法加载本地模型")
                self.model = None
                
        except Exception as e:
            logger.error(f"加载本地模型失败: {str(e)}")
            self.model = None
            
    def _get_embedding_with_local_model(self, text: str) -> List[float]:
        """
        使用本地模型获取嵌入向量
        
        Args:
            text: 输入文本
            
        Returns:
            List[float]: 嵌入向量
        """
        # 这里实现使用本地模型的嵌入逻辑
        # 示例：使用ONNX模型
        try:
            if hasattr(self.model, "run"):
                # 预处理文本
                # 简单实现，实际应该根据模型要求进行预处理
                inputs = {"input_ids": [ord(c) for c in text[:512]]}
                
                # 运行模型
                outputs = self.model.run(None, inputs)
                
                # 返回嵌入向量
                embedding = outputs[0].tolist()[0]
                return embedding
            else:
                logger.error("模型未正确加载，无法获取嵌入向量")
                return None
        except Exception as e:
            logger.error(f"使用本地模型获取嵌入向量失败: {str(e)}")
            return None
            
    def get_cache_stats(self) -> Dict:
        """
        获取缓存统计信息
        
        Returns:
            Dict: 缓存统计信息
        """
        return {
            "hits": self.cache_hits,
            "misses": self.cache_misses,
            "size": len(self.cache),
            "max_size": self.max_cache_size
        }

# 重排序器实现
class ApiReranker:
    """API重排序器"""
    
    def __init__(self, api_wrapper, model_name):
        """
        初始化API重排序器
        
        Args:
            api_wrapper: API调用包装器
            model_name: 模型名称
        """
        self.api_wrapper = api_wrapper
        self.model_name = model_name
        
    async def rerank(self, query: str, results: List[Dict]) -> List[Dict]:
        """
        重排序检索结果
        
        Args:
            query: 查询文本
            results: 检索结果列表
            
        Returns:
            List[Dict]: 重排序后的结果列表
        """
        try:
            if not self.api_wrapper:
                logger.error("API包装器未初始化，无法进行重排序")
                return results
                
            if not results or len(results) <= 1:
                return results
                
            # 使用LLM进行重排序
            prompt = self._create_rerank_prompt(query, results)
            
            response = await self.api_wrapper.async_completion(
                prompt=prompt,
                temperature=0.1,
                max_tokens=500
            )
            
            # 解析重排序结果
            reranked_results = self._parse_rerank_response(response.get("content", ""), results)
            
            # 如果解析失败，返回原始结果
            if not reranked_results:
                return results
                
            return reranked_results
        except Exception as e:
            logger.error(f"重排序失败: {str(e)}")
            return results
            
    def _create_rerank_prompt(self, query: str, results: List[Dict]) -> str:
        """
        创建重排序提示
        
        Args:
            query: 查询文本
            results: 检索结果列表
            
        Returns:
            str: 重排序提示
        """
        prompt = f"""请根据查询问题对以下文档片段进行相关性排序，从最相关到最不相关。
仅基于文档与查询的相关性进行排序，不考虑文档的其他方面。

查询问题: {query}

文档片段:
"""

        for i, result in enumerate(results):
            content = result.get("content", "")
            prompt += f"\n文档{i+1}: {content}\n"
            
        prompt += """
请按相关性从高到低列出文档编号，使用以下格式:
排序结果: [最相关文档编号], [次相关文档编号], ...
"""
        
        return prompt
        
    def _parse_rerank_response(self, response: str, results: List[Dict]) -> List[Dict]:
        """
        解析重排序响应
        
        Args:
            response: LLM响应文本
            results: 原始检索结果
            
        Returns:
            List[Dict]: 重排序后的结果列表
        """
        try:
            # 提取排序结果
            import re
            match = re.search(r'排序结果:?\s*(.+)', response)
            
            if not match:
                logger.warning("未能从响应中提取排序结果")
                return []
                
            # 解析文档编号
            order_text = match.group(1)
            order_parts = re.findall(r'\d+', order_text)
            
            if not order_parts:
                logger.warning("未能解析文档编号")
                return []
                
            # 将文本编号转换为整数索引
            try:
                orders = [int(part) - 1 for part in order_parts]
            except ValueError:
                logger.warning("文档编号解析错误")
                return []
                
            # 按照排序重组结果
            reranked_results = []
            seen_indices = set()
            
            for idx in orders:
                if 0 <= idx < len(results) and idx not in seen_indices:
                    reranked_results.append(results[idx])
                    seen_indices.add(idx)
                    
            # 添加未包含在排序中的结果
            for i, result in enumerate(results):
                if i not in seen_indices:
                    reranked_results.append(result)
                    
            return reranked_results
        except Exception as e:
            logger.error(f"解析重排序响应失败: {str(e)}")
            return []

# 存储实现
class JsonStorage:
    """JSON文件存储"""
    
    def __init__(self, file_path):
        """
        初始化JSON存储
        
        Args:
            file_path: JSON文件路径
        """
        self.file_path = file_path
        self.data = self._load_data()
        
        # 添加维度缓存
        self.dimension_cache = {}
        
    def _load_data(self) -> Dict:
        """
        加载数据
        
        Returns:
            Dict: 数据字典
        """
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 确保基本结构存在
                    if "documents" not in data:
                        data["documents"] = []
                    if "group_chats" not in data:
                        data["group_chats"] = {}
                    return data
            else:
                # 初始化空数据
                data = {
                    "documents": [],
                    "group_chats": {}  # 添加群聊数据结构
                }
                self._save_data(data)
                return data
        except Exception as e:
            logger.error(f"加载数据失败: {str(e)}")
            return {"documents": [], "group_chats": {}}
            
    def _save_data(self, data: Dict = None):
        """
        保存数据
        
        Args:
            data: 要保存的数据字典
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            
            # 如果未提供数据，使用当前数据
            if data is None:
                data = self.data
                
            # 保存数据
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败: {str(e)}")
            
    def add_document(self, document: Dict) -> bool:
        """
        添加文档
        
        Args:
            document: 文档字典
            
        Returns:
            bool: 是否成功添加
        """
        try:
            # 检查文档ID是否已存在
            doc_id = document.get("id")
            
            for existing_doc in self.data["documents"]:
                if existing_doc.get("id") == doc_id:
                    # 更新现有文档
                    existing_doc.update(document)
                    self._save_data()
                    return True
                    
            # 添加新文档
            self.data["documents"].append(document)
            self._save_data()
            return True
        except Exception as e:
            logger.error(f"添加文档失败: {str(e)}")
            return False
            
    def search(self, query_embedding: List[float], top_k: int = 5, avatar_name: str = None) -> List[Dict]:
        """
        搜索相关文档
        
        Args:
            query_embedding: 查询嵌入向量
            top_k: 返回结果数量
            avatar_name: 角色名，如果提供则只搜索该角色的记忆
            
        Returns:
            List[Dict]: 相关文档列表
        """
        try:
            if not self.data["documents"]:
                return []
                
            # 计算余弦相似度
            results = []
            
            for doc in self.data["documents"]:
                # 如果指定了角色名，则只检索该角色的记忆
                if avatar_name and doc.get("metadata", {}).get("user_id") != avatar_name:
                    continue
                    
                doc_embedding = doc.get("embedding")
                
                if not doc_embedding:
                    continue
                    
                # 计算相似度
                similarity = self._cosine_similarity(query_embedding, doc_embedding)
                
                # 添加到结果列表
                results.append({
                    "id": doc.get("id"),
                    "content": doc.get("content"),
                    "metadata": doc.get("metadata", {}),
                    "score": similarity
                })
                
            # 按相似度降序排序
            results.sort(key=lambda x: x["score"], reverse=True)
            
            # 返回前top_k个结果
            return results[:top_k]
        except Exception as e:
            logger.error(f"搜索文档失败: {str(e)}")
            return []
            
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        计算余弦相似度
        
        Args:
            vec1: 向量1（查询向量）
            vec2: 向量2（记忆向量）
            
        Returns:
            float: 余弦相似度
        """
        try:
            # 转换为numpy数组
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            # 检查向量维度是否匹配
            if vec1.shape[0] != vec2.shape[0]:
                # 构建缓存键
                cache_key = f"{vec1.shape[0]}_{vec2.shape[0]}"
                
                # 如果这种维度组合已经警告过，不再重复警告
                if cache_key not in self.dimension_cache:
                    logger.debug(f"向量维度不匹配: {vec1.shape} vs {vec2.shape}，尝试调整")
                    self.dimension_cache[cache_key] = True
                
                # 优先以记忆向量（vec2）的维度为准
                target_dim = vec2.shape[0]
                
                # 如果查询向量维度过小，无法调整到记忆向量维度，则放弃计算
                if vec1.shape[0] < target_dim:
                    if cache_key + "_pad" not in self.dimension_cache:
                        logger.debug(f"查询向量维度({vec1.shape[0]})小于记忆向量维度({target_dim})，填充零值")
                        self.dimension_cache[cache_key + "_pad"] = True
                    # 填充查询向量到目标维度
                    padding = np.zeros(target_dim - vec1.shape[0])
                    vec1 = np.concatenate([vec1, padding])
                else:
                    # 截断查询向量以匹配记忆向量维度
                    vec1 = vec1[:target_dim]
                
                if cache_key + "_info" not in self.dimension_cache:
                    logger.debug(f"向量维度已调整: 查询向量调整为记忆向量维度 {vec2.shape[0]}")
                    self.dimension_cache[cache_key + "_info"] = True
            
            # 计算点积
            dot_product = np.dot(vec1, vec2)
            
            # 计算范数
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            # 避免除以零
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            # 计算相似度
            similarity = dot_product / (norm1 * norm2)
            
            return float(similarity)
        except Exception as e:
            logger.error(f"计算余弦相似度失败: {str(e)}")
            return 0.0
            
    def get_document_count(self, avatar_name: str = None) -> int:
        """
        获取文档数量
        
        Args:
            avatar_name: 角色名，如果提供则只计算该角色的记忆数量
            
        Returns:
            int: 文档数量
        """
        if avatar_name:
            return len([doc for doc in self.data.get("documents", []) 
                       if doc.get("metadata", {}).get("user_id") == avatar_name])
        return len(self.data.get("documents", []))
        
    def get_latest_documents(self, limit: int = 20, avatar_name: str = None) -> List[Dict]:
        """
        获取最新文档
        
        Args:
            limit: 返回的文档数量
            avatar_name: 角色名，如果提供则只返回该角色的记忆
            
        Returns:
            List[Dict]: 文档列表
        """
        try:
            documents = self.data.get("documents", [])
            
            # 如果指定了角色名，只获取该角色的文档
            if avatar_name:
                documents = [doc for doc in documents 
                           if doc.get("metadata", {}).get("user_id") == avatar_name]
            
            # 如果数据中包含创建时间，按时间排序
            try:
                documents_with_time = []
                
                for doc in documents:
                    # 尝试从元数据中获取时间
                    metadata = doc.get("metadata", {})
                    timestamp = metadata.get("timestamp", "")
                    
                    # 如果没有时间信息，尝试从ID中提取
                    if not timestamp and "memory_" in doc.get("id", ""):
                        try:
                            time_part = doc.get("id", "").split("memory_")[1]
                            timestamp = time_part
                        except:
                            pass
                            
                    # 添加到列表
                    documents_with_time.append((doc, timestamp))
                    
                # 按时间戳降序排序（最新的在前面）
                documents_with_time.sort(key=lambda x: x[1], reverse=True)
                
                # 提取文档
                sorted_documents = [doc for doc, _ in documents_with_time]
                return sorted_documents[:limit]
            except Exception as e:
                logger.error(f"排序文档失败: {str(e)}")
                
            # 如果排序失败，直接返回最新的文档
            return documents[-limit:]
        except Exception as e:
            logger.error(f"获取最新文档失败: {str(e)}")
            return []
            
    def clear(self, avatar_name: str = None) -> bool:
        """
        清空存储
        
        Args:
            avatar_name: 角色名，如果提供则只清空该角色的记忆
            
        Returns:
            bool: 是否成功清空
        """
        try:
            if avatar_name:
                # 只清空指定角色的记忆
                self.data["documents"] = [doc for doc in self.data.get("documents", [])
                                        if doc.get("metadata", {}).get("user_id") != avatar_name]
            else:
                # 清空所有记忆
                self.data = {"documents": []}
            
            self._save_data()
            return True
        except Exception as e:
            logger.error(f"清空存储失败: {str(e)}")
            return False

def create_default_config(config_path: str):
    """
    创建默认RAG配置文件
    
    Args:
        config_path: 配置文件路径
    """
    try:
        default_config = {
            "api_key": "",
            "base_url": "",
            "embedding_model": {
                "type": "openai",
                "name": "text-embedding-3-large",
                "dimensions": 1536
            },
            "storage": {
                "type": "json",
                "path": "./data/rag_storage.json"
            },
            "top_k": 5,
            "is_rerank": False,
            "reranker": {
                "type": "api",
                "name": "rerank-large"
            },
            "local_model": {
                "enabled": False,
                "path": "./models/embedding_model"
            }
        }
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # 保存配置
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
            
        logger.info(f"已创建默认RAG配置文件: {config_path}")
        return default_config
    except Exception as e:
        logger.error(f"创建默认配置文件失败: {str(e)}")
        return None

# 添加必要的导入
import re  # 用于正则表达式操作 