# v0.2：Interactive Market Sandbox - 共享设计

本文只记录 v0.2 跨里程碑技术约束。0.2.1 的具体接口、状态机、输入记录和测试方案见
[`0.2.1 design`](0.2.1-interactive-sandbox/design.md)。

## 1. 技术上下文

v0.2 复用 v0.1 的 L1—L4 分层、订单簿、账本、事件调度、事件日志与离线回放。新增能力
位于内核外侧：交互会话控制器接收人类输入，把已接受动作转换为现有代理/订单入口；本地
客户端只调用会话接口，不直接修改订单簿或账户。

## 2. 跨里程碑边界

```text
local client
    -> interactive session controller
        -> human input adapter
            -> existing agent / order / risk path
                -> event log -> replay / bundle
```

- 会话控制器拥有墙钟节流、暂停/继续、输入排序与规范输入日志。
- 确定性内核只接收已分配逻辑时间的动作，不读取墙钟。
- 现有事件日志仍是市场状态与回放的唯一真源；输入日志只拥有外生输入序列。
- 正式研究入口必须在消费任何交互产物前校验 `run_mode` 并 fail closed。

## 3. 共享不变量

- 相同代码、配置、种子与规范输入序列产生相同事件摘要哈希。
- 每个人类市场动作只通过一个现有生产入口进入内核，不建立 UI 专用撮合路径。
- 暂停只停止逻辑时间推进，不回滚已提交事务。
- wall-clock 元数据不参与市场判定、事件摘要或重放相等性。
- `interactive` 产物不得升级为 `experiment-preview` 或 `formal-research`。

## 4. 兼容与演进

- H1 默认本机单进程；接口保持 UI 技术无关，以便将来替换客户端。
- 需要修改事件 Schema 时，须先更新合同与 schema version，再实现消费者。
- H2 将复用输入与会话记录，但其分组、权限、窗口和排除规则不在本设计中预定义。

