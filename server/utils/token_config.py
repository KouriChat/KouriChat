import os
import time
import jwt
from typing import Optional
from flask import abort

class TokenConfig:
    SECRET_KEY = os.getenv('JWT_SECRET', 'mysecretkey')
    ALGORITHM = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

    @classmethod
    def generate_token(cls, user_id: str) -> str:
        payload = {
            'user_id': user_id,
            'exp': time.time() + cls.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        return jwt.encode(payload, cls.SECRET_KEY, algorithm=cls.ALGORITHM)

    @classmethod
    def verify_token(cls, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, cls.SECRET_KEY, algorithms=[cls.ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            abort(401, description="Token已过期")
        except jwt.InvalidTokenError:
            abort(401, description="无效的Token")