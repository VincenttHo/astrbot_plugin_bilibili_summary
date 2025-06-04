<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_bilibili_summary?name=astrbot_plugin_bilibili_summary&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

</div>

# Bilibili视频字幕总结插件

这是一个AstrBot插件，可以获取Bilibili视频的字幕并使用LLM生成内容总结。节省你的时间！

## 功能特性

- 🎬 支持多种Bilibili视频链接格式（BV号、AV号、完整链接、短链接）
- 🤖 使用LLM生成视频内容总结
- 🌏 优先选择中文字幕，支持多语言字幕
- ⚙️ 可配置的API参数和请求间隔
- 🛡️ 内置风控保护机制

## 安装方法

### 方法一：通过AstrBot界面的插件市场安装

1. 在AstrBot管理界面中，进入"插件市场"
2. 搜索 `astrbot_plugin_bilibili_summary`
3. 点击安装即可

### 方法二：手动安装

1. 克隆或下载插件代码到AstrBot的插件目录：
```bash
cd AstrBot/data/plugins
git clone https://github.com/VincenttHo/astrbot_plugin_bilibili_summary
```

2. 重启AstrBot或在管理面板中重载插件

## 配置说明

在AstrBot管理面板中配置以下参数：

### 必需配置 <font color='red'>（重要）</font>
- **OpenAI API密钥**: 用于调用LLM生成总结的API密钥
- **OpenAI API地址**: 默认为OpenAI官方地址，可配置为其他兼容接口
- **使用的模型**: 默认为gpt-3.5-turbo
- **Bilibili SESSDATA**: 从浏览器Cookie中获取，用于访问需要登录的API

#### 如何获取Bilibili SESSDATA？

1. 打开浏览器，登录Bilibili
2. 按F12打开开发者工具
3. 切换到"Application"或"应用程序"标签
4. 在左侧找到"Cookies" -> "https://www.bilibili.com"
5. 找到名为"SESSDATA"的Cookie，复制其值
6. 将该值填入插件配置中

### 可选配置
- **请求间隔**: 两次API请求之间的间隔时间，避免触发风控
- **最大字幕长度**: 提交给LLM的字幕最大字符数
- **总结提示词**: 用于指导LLM生成总结的提示词


## 使用方法

### 基本命令

```
/bs [视频链接或ID]
```

支持多种格式：
```
# BV号
/bs BV1jv7YzJED2
/bs 1jv7YzJED2

# AV号
/bs av123456
/bs 123456

# 完整链接
/bs https://www.bilibili.com/video/BV1jv7YzJED2
/bs https://m.bilibili.com/video/BV1jv7YzJED2

# 短链接
/bs https://b23.tv/xxxxx
```

## 注意事项

- 获取视频字幕信息需要登录状态，请确保配置了有效的SESSDATA
- 请求过于频繁可能触发Bilibili的风控机制，建议适当设置请求间隔
- 部分视频可能没有字幕或字幕需要特殊权限，这类视频不支持总结（就是视频右下角有没有“字幕”选项）
- 请遵守Bilibili的使用条款和相关法律法规


## 使用示例

![使用示例图](https://raw.githubusercontent.com/VincenttHo/astrbot_plugin_bilibili_summary/refs/heads/main/images/sample.jpg)

## 版本历史

- v1.0.0: 初始版本，支持多种格式搜索视频并进行总结。