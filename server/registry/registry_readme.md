# Registry 说明
## 1. 简介

 从 **KouriChat v2.0** 开始，我们希望可以将 KouriChat 的所有模块解耦
  因此，我们需要一个统一的**模块管理系统**，即 **Registry**
  Registry 是一个模块管理系统，它可以管理所有的模块，并且实现模块的动态加载
  Registry 可以将模块注册到 Registry 中，也可以从 Registry 中获取模块

>
Registry 通过配置文件映射表的方式去实现动态模块开启，在保存基本模块可以正常使用时，其余所有模块都应当是用户可以自选的

## 2. 配置文件

 Registry 会在启动时自动加载配置文件，配置文件的路径为 `config/registry.yaml`
 配置文件的格式为 YAML, 配置文件的内容为一个字典
 配置文件的内容示例如下：
```yaml
modules:
    base:
        dialogue: 
            path: processors/dialogue
        emotion:
            path: processors/emotion
        memory:
            path: processors/memory
    user:
        game:
            value: true
            path: modules/user/game

```
base 模块为基础模块，user 模块为用户模块
基础模块为**必须加载**的模块，用户模块为可选加载的模块。 value 为是否加载，path 为模块的路径
基础模块可以增加，更改，**但是必须保留一个模块作为调用**
用户模块可以增加，更改，无更多要求
