# 用 WeFlow 导出微信聊天记录

1. 下载 [WeFlow](https://github.com/hicccc77/WeFlow) 并安装
2. 打开 WeFlow，用微信扫码登录
3. 选择要导出的私聊会话 → 导出为 JSON（选择「包含双方消息」）
4. 得到一个 `.json` 文件，即可作为 `alchemy-hive import` 的输入

## 支持的文件格式

- **WeFlow 导出 JSON**：顶层数组或 `{messages:[...]}`；字段兼容 `msgContent/content/text`、`isSend/senderUsername` 等常见命名
- **微信导出 TXT**：`时间戳 '发送者'` + 内容 的多行格式
