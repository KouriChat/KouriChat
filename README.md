# 🌸 KouriChat - 在虚拟与现实交织处，给予永恒的温柔羁绊

#### 本仓库为​**开发分支**​，包含新的​**实验性特性**​。若非开发人员**请勿**直接使用此分支，​**否则您的问题可能无法得到答复**​。

[![GitHub Stars](https://img.shields.io/github/stars/KouriChat/KouriChat?style=for-the-badge&logo=starship&color=ff69b4)](https://github.com/KouriChat/KouriChat/stargazers)
[![License](https://img.shields.io/badge/license-FSL-informational?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=2B5B84)](https://www.python.org/downloads/)
[![Community](https://img.shields.io/badge/QQ群-715616260-12B7F3?style=for-the-badge&logo=tencentqq)](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)


[![Moe Counter](https://count.getloli.com/get/@KouriChat?theme=moebooru)](https://github.com/KouriChat/KouriChat)



**最新整合包**：[夸克网盘下载](https://pan.quark.cn/s/c55dd13218ea)<br>
**详细文档**：[项目官网](https://kourichat.com/docs/)<br>
**角色广场已上线！**：[角色档案馆](https://avatars.kourichat.com/#/archive)
**项目直属公益API（推荐，低价）**: [Kouri API](https://api.kourichat.com/)
----------------------------

## 🌟 效果示例

<div align="center">
  <img src="data/images/img/demo.png" width="600" alt="演示效果">
</div>

### 🚀 部署推荐

- 通过[夸克网盘](https://pan.quark.cn/s/c55dd13218ea)下载项目，推荐转存，第一时间获得更新，我也会有收益
- 最好有一台Windows Server服务器挂机，[雨云服务器五折券](https://www.rainyun.com/MzE0MTU=_)
- [项目直属公益API（推荐，低价）](https://api.kourichat.com/)
- [获取DeepSeek API Key](https://cloud.siliconflow.cn/i/aQXU6eC5)（免费15元额度）

---

## 📜 项目声明

**法律与伦理准则**
▸ 本项目仅供技术研究与学习交流
▸ 禁止用于任何违法或违反道德的场景
▸ 生成内容不代表开发者立场

**使用须知**
▸ 角色版权归属原始创作者
▸ 使用者需对自身行为负全责
▸ 未成年人应在监护下使用

---

## 🛠️ 功能全景

### ✅ 已实现

- 微信无缝接入 & 多用户支持
- 沉浸式角色扮演（支持群聊）
- 智能对话分段 & 情感化表情包
- 图像生成 & 图片识别（Kimi集成）
- 语音消息 & 持久记忆存储
- 自动更新 & 可视化WebUI

### 🚧 开发中

- 智能定时任务系统
- 记忆整理优化（8B小模型）
- 分布式负载均衡
- 数学公式渲染引擎
- OneBot协议兼容
- [参与开发计划](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)

---

## 🚀 快速启动

### 环境准备

1. **备用设备**：手机/模拟器/双开应用（微信电脑端登录必须有一个移动设备同时登录）
2. **微信小号**：能登录PC版即可
3. **API密钥**：

- [项目直属公益API（推荐）](https://api.kourichat.com/)（注册送20刀，签到送1-5刀）
- [获取DeepSeek API Key](https://cloud.siliconflow.cn/i/aQXU6eC5)（免费15元额度）

### 部署流程

#### 半自动部署流程

```bash
运行 run.bat
```

#### 手动部署流程

```bash
# 克隆仓库
git clone https://github.com/KouriChat/KouriChat.git

# 更新pip
python -m pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple --upgrade pip

# 安装依赖
pip install -r requirements.txt

#调整配置文件
python run_config_web.py

# 启动程序 或 使用WebUI启动 (在此之前，请启动微信！不然会提示未找到窗口句柄...）
python run.py
```

---

## 🧩 项目架构

```
KouriChat/
├── avatars/                      # 角色配置文件
├── data/                         # 运行数据存储
├── src/
│   ├── handlers/                # 功能处理器
│   ├── services/                # AI服务接口
│   ├── webui/                   # 可视化配置界面
│   └── utils/                   # 工具库
└── version.json                 # 版本管理
```

---

## 💖 支持我们

<div align="center">
  <!-- 项目星标 -->
  <p>点击星星助力项目成长 ⭐️ → 
    <a href="https://github.com/KouriChat/KouriChat">
      <img src="https://img.shields.io/github/stars/KouriChat/KouriChat?color=ff69b4&style=flat-square" alt="GitHub Stars">
    </a>
  </p>

<!-- 资金用途 -->

<p style="margin:18px 0 10px; font-size:0.95em">
    🎯 您的支持将用于：<br>
    🚀 服务器费用 • 🌸 API资源 • 🛠️ 功能开发 • 💌 社区运营
  </p>

<!-- 赞助二维码 -->

<img src="data/images/img/qrcode.jpg" width="450" alt="支持二维码" style="border:3px solid #eee; border-radius:12px">

<!-- 神秘计划模块 -->

<div style="font-size:0.88em; line-height:1.3; max-width:540px; margin:15px auto;
              background: linear-gradient(145deg, rgba(255,105,180,0.08), rgba(156,39,176,0.05));
              padding:10px 15px; border-radius:6px; border:1px solid rgba(255,105,180,0.15)">
    <span style="color: #9c27b0">🔒 神秘赞助计划：</span>
    <span style="margin-left:6px; letter-spacing:-0.5px">
      <i class="fa fa-lock" style="color: #ff4081; margin-right:4px"></i>
      <span style="background: linear-gradient(45deg, #ff69b4, #9c27b0); -webkit-background-clip: text; color: transparent">
        限定数字藏品·开发者礼包·神秘周边·▮▮▮▮
      </span>
    </span>
  </div>

<!-- 动态徽章 -->

<div style="margin:18px 0 8px">
    <img src="https://img.shields.io/badge/已解锁成就-▮▮▮▮▮▮-ff69b4?style=flat-square&logo=starship">
    <img src="https://img.shields.io/badge/特别鸣谢-▮▮▮▮▮▮-9c27b0?style=flat-square&logo=heart">
  </div>
</div>

---

## 🌐 社区互动

### 核心交流群

[![主群](https://img.shields.io/badge/✨_主群-715616260-4FC3F7?style=for-the-badge&logo=tencentqq&logoColor=white&labelColor=006699)](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)
[![二群](https://img.shields.io/badge/🎮_二群-1031640399-76D7C4?style=for-the-badge&logo=tencentqq&logoColor=white&labelColor=00897B)](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)
[![二群](https://img.shields.io/badge/🎮_三群-1038190753-76D7C4?style=for-the-badge&logo=tencentqq&logoColor=white&labelColor=00897B)](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)
[![赞助群](https://img.shields.io/badge/💰_赞助群-953908612-FFEA00?style=for-the-badge&logo=tencentqq&logoColor=333&labelColor=FFD600)](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)
[![QQ频道](https://img.shields.io/badge/📢_QQ频道-和Ai恋爱吧-B2EBF2?style=for-the-badge&logo=tencentqq&logoColor=white&labelColor=00B8D4)](https://pd.qq.com/s/4zthl285m)

### 通过其他方式联系我们

- **开发讨论**：[功能建议 & Bug反馈](https://jq.qq.com/?_wv=1027&k=5z4Q0i7o)
- **视频教程**：[哔哩哔哩频道](https://space.bilibili.com/209397245)
- **技术文档**：[KouriChat Wiki](https://kourichat.com/docs)
- **商务合作**：[yangchenglin2004@foxmail.com](mailto:yangchenglin2004@foxmail.com)

---

<div align="center">
  <sub>🛠️ 核心技术栈</sub>
  <br>
  <a href="https://www.python.org/" target="_blank">
    <img src="https://img.shields.io/badge/Python-3.11_➔_3.12-0073B7?logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://github.com/cluic/wxauto" target="_blank">
    <img src="https://img.shields.io/badge/wxauto-自动化框架-0099E5?logo=wechat&logoColor=white" alt="wxauto">
  </a>

</div>

[![Star History](https://api.star-history.com/svg?repos=KouriChat/KouriChat&type=Timeline)](https://star-history.com/#KouriChat/KouriChat)

