from config import EMBEDDING_MODEL, EMBEDDING_FALLBACK_MODEL
import config

def get_embedding(text, model=EMBEDDING_MODEL):
    try:
        response = openai.Embedding.create(
            input=text,
            model=model
        )
        return response['data'][0]['embedding']
    except Exception as e:
        logger.error(f"嵌入失败: {str(e)}")
        if model != EMBEDDING_FALLBACK_MODEL:
            logger.info(f"尝试使用备用模型 {EMBEDDING_FALLBACK_MODEL}")
            return get_embedding(text, EMBEDDING_FALLBACK_MODEL)
        else:
            raise 