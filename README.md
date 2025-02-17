![ATRI.jpg](data%2Fimages%2Fimg%2FATRI.jpg)

有问题可加群：715616260 

- 一键整合包夸克网盘：https://pan.quark.cn/s/f37d765e1404 提取码：zXpP 推荐转存，项目更新直接下载最新的代码zip。我也能有收益，感谢您的支持！
- 部署项目推荐使用Windows服务器，[雨云优惠通道注册送首月五折券](https://www.rainyun.com/MzE0MTU=_) 
- 获取 DeepSeek API Key，[获取 API Key（15元免费额度）](https://cloud.siliconflow.cn/i/aQXU6eC5)

---

## 简介

简体中文 · [English](./README_EN.md) 

- 已经更换了安全的微信自动化方案，即<code>wxauto</code>，封号可能性几乎没有，稳定性拉满
- My Dream Moments 是一个基于大型语言模型（LLM）的情感陪伴程序，能够接入微信，提供更真实的情感交互体验。内置了 Atri-My dear moments 的 prompt，并且解决了传统人机对话程序一问一答的死板效果，提供沉浸式角色扮演和多轮对话支持。项目名字来源是运行在该程序上的第一个智能体的原作名称+项目价值观混合而来。
- 推荐使用DeepSeek V3 模型。<br>
- [里程碑](MileStone.md)
- [致谢](Thanks.md)<br>
  ![demo.png](data%2Fimages%2Fimg%2Fdemo.png)

---

## 声明

- 本项目仅用于交流学习，LLM发言不代表作者本人立场。prompt所模仿角色版权归属原作者。任何未经许可进行的限制级行为均由使用者个人承担。

---

## 已实现的功能

- [x] 对接微信，沉浸式角色扮演
- [x] 聊天分段响应，消除人机感
- [x] 多轮对话
- [x] 多用户支持
- [x] 由 DeepSeek R1 利用游戏文本生成的 Prompt
- [x] 无需联网的时间感知
- [x] WebUI，方便不理解代码的用户配置项目
- [x] 图像生成
- [x] 异步请求
- [x] 实现群聊
- [x] 表情包
- [x] Ai图片识别，调用kimi
- [x] 实现R1对话
- [x] 实现主动发消息
- [x] 语音功能，暂时发送wav语言文件
- [x] 完善WebUi
- [x] 实现持久记忆
- [x] 自动更新
- [x] AI根据情感输出表情包
- [x] 运行src/autoupdate/updater.py可以一键更新 
---

## 待实现功能，期待您的加入

- [ ] 定时任务与智能定时任务
- [ ] 利用 8B 小模型实时生成记忆并定期整理
- [ ] 负载均衡
- [ ] 数学公式或者代码实现远程渲染
- [ ] 官方文档
- [ ] 人设web页面，各种人设和允许用户上传prompt
---


## 如何运行项目

### 1. 前期准备

1. **备用手机/安卓模拟器**  
   - 微信电脑端登录必须有一个移动设备同时登录，因此不能使用您的主要设备。

2. **微信小号**  
   - 可以登录微信电脑版即可。

3. **DeepSeek API Key**  
   - 推荐使用：[获取 API Key（15元免费额度）](https://cloud.siliconflow.cn/i/aQXU6eC5)

---

### 2. 部署项目

1. **克隆本仓库**  

   ```bash
   git clone https://github.com/umaru-233/My-Dream-Moments.git
   ```

2. **安装pip** 

   ```bash
   python -m ensurepip
   ```

3. **安装依赖**  

   ```bash
   pip install -r requirements.txt
   ```

4. **配置<code>src/config/settings.py</code>**  
   修改<code>LISTEN_LIST</code>、<code>DEEPSEEK_BASE_URL</code>和<code>DEEPSEEK_API_KEY</code>。

按需调整<code>MAX_TOKEN</code>、<code>TEMPERATURE</code>和<code>MODEL</code>。如何配置请阅读<code>config.py</code>里的注释。

5. **运行<code>run.py</code>，如果报错请尝试使用Python 3.11版本。**

   ```bash
   python run.py
   ```

6. FAQ:没什么问题是重启解决不了的，如果重启解决不了，请重启


### 3. 如何使用

- **使用微信小号登录微信电脑版**

- **项目运行后，控制台提示**

  ```bash
  初始化成功，获取到已登录窗口：<您的微信昵称>
  开始运行BOT...
  ```

  即可开始监听并调用模型自动回复消息。

## 如果您想修改prompt

- 修改avatars/ATRI/ATRI.md的内容
- 注意：请不要修改与反斜线 <code> \ </code>相关的 prompt，因为它们被用于分段回复消息。

结构说明：

```python
My-Dream-Moments/
├── data/                           # 数据存储目录
├── logs/                           # 日志目录
├── src/                            # 源代码主目录
│   ├── autoupdate/                # 自动更新相关
│   │   └── updater.py            # 更新器实现
│   │
│   ├── config/                    # 配置文件目录
│   │   ├── config.json           # JSON配置文件
│   │   ├── settings.py           # 设置模块
│   │   └── __init__.py           # 配置初始化
│   │
│   ├── handlers/                  # 处理器目录
│   │   ├── emoji.py              # 表情处理
│   │   ├── image.py              # 图片处理
│   │   ├── memory.py             # 内存处理
│   │   ├── message.py            # 消息处理
│   │   └── voice.py              # 语音处理
│   │
│   ├── services/                  # 服务层目录
│   │   ├── ai/                   # AI服务目录
│   │   └── database.py           # 数据库服务
│   │
│   ├── utils/                     # 工具函数目录
│   │   ├── cleanup.py            # 清理工具
│   │   └── logger.py             # 日志工具
│   │
│   ├── webui/                     # Web界面相关
│   │   ├── background_image/     # 背景图片目录
│   │   ├── routes/               # 路由目录
│   │   └── templates/            # 模板目录
│   │       ├── config.html       # 配置页面
│   │       └── config_item.html  # 配置项模板
│   │
│   ├── main.py                    # 核心业务逻辑
│   └── __init__.py                # 包初始化文件
│
├── .git/                           # Git版本控制目录
├── .gitignore                     # Git忽略配置
├── LICENSE                        # 开源许可证
├── MileStone.md                  # 项目里程碑
├── README.md                     # 中文说明文档
├── README_EN.md                  # 英文说明文档
├── SponsorList.md                # 赞助者名单
├── Thanks.md                     # 致谢文档
├── a点我启动程序.bat               # Windows启动脚本
├── requirements.txt              # 依赖包列表
├── run.py                        # 主程序入口
├── run_config_web.py             # Web配置界面入口
├── test.py                       # 测试文件
└── version.json                  # 版本信息配置
```



## 赞助

此项目欢迎赞助。您的支持对我非常重要！

- 赞助用户如需远程部署或定制 prompt，请联系我。
- E-Mail: yangchenglin2004@foxmail.com 
- Bilibili: [umaru今天吃什么](https://space.bilibili.com/209397245)
- 感谢您的支持与使用！!<br>
  ![qrcode.jpg](data%2Fimages%2Fimg%2Fqrcode.jpg)

## 请给我Star，这对我很重要TvT

- [![Star History Chart](https://api.star-history.com/svg?repos=umaru-233/My-Dream-Moments&type=Timeline)](https://star-history.com/?spm=a2c6h.12873639.article-detail.8.7b9d359dJmTgdE#umaru-233/My-Dream-Moments&Timeline)
