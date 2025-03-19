# kourichat-config-server

重构版 kourichat 的配置端

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行项目

```bash
python main.py
```

或者使用 uvicorn 直接运行：

```bash
uvicorn main:app --reload
```

## API 文档

启动服务后，可以访问以下地址查看 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
