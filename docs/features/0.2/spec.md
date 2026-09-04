---
kind: version-spec
id: v0.2-interactive-market-sandbox
version: "0.2"
status: done
research_claim_status: not-applicable
research_claim_required: false
evidence_class: engineering-demonstration
created: 2026-09-01
updated: 2026-09-01
---

# Feature Specification: Interactive Market Sandbox

**规格编号**：v0.2-interactive-market-sandbox<br>
**关联 PRD**：[`../../market-game-sim-prd.md`](../../market-game-sim-prd.md) §15 H1<br>
**架构**：[`design.md`](design.md)<br>
**首个里程碑**：[`0.2.1`](0.2.1-interactive-sandbox/spec.md)

## 问题与目标

v0.1 已能运行、审计并离线回放纯代理市场，但交易者不能在运行中观察市场并亲自提交或
撤销订单。v0.2 的第一个目标是在不削弱确定性、撮合正确性和研究证据隔离的前提下，交付
一个本地手动交易沙盒。

本版本把确定性扩展为「相同代码 + 配置 + 种子 + 规范输入序列」，并保持逻辑时间为唯一
市场时间。墙钟只控制呈现与节流，不进入撮合、账本或重放判定。

## 非目标

- 不连接真实交易所、券商、钱包、账户或资金，不生成交易信号或投资建议。
- 不把 `interactive` 运行用于统计推断、研究声明或 v0.1 证据补充。
- 不在 H1 中开展随机分组、学习/疲劳效应或人在环正式实验；这些属于 H2 独立规格。
- 不实现多用户、远程服务、身份系统、排行榜、移动端或公网部署。
- 不引入股票式制度、多品种、订单流预知者或策略在线学习。

## 用户场景

### US-201：完成一次手动交易会话（P1）

作为交易者，我可以完成一次本地手动交易闭环。场景正文见
[`0.2.1 spec`](0.2.1-interactive-sandbox/spec.md#2-用户场景)。

### US-202：保存并重放决策链（P1）

作为交易者，我可以保存并确定性重放输入及其市场后果。场景正文见
[`0.2.1 spec`](0.2.1-interactive-sandbox/spec.md#2-用户场景)。

### US-203：确认研究隔离（P1）

作为研究者，我可以机器确认交互产物不会进入正式研究证据。场景正文见
[`0.2.1 spec`](0.2.1-interactive-sandbox/spec.md#2-用户场景)。

## 功能需求

- **FR-201**：创建可识别的交互会话；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-202**：限制人类观察信息面；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-203**：人类动作复用生产订单路径；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-204**：提供确定性的会话控制与输入排序；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-205**：保存并确定性重放规范输入序列；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-206**：正式研究消费者 fail-closed 拒绝交互产物；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-207**：本地客户端呈现完整交易与会话反馈；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **FR-208**：生成同源、可审计、可离线打开的成果包；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。

## 数据、事件与接口需求

- **TR-201**：规范输入记录与排序合同；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **TR-202**：人类决定沿用既有事件因果链；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **TR-203**：manifest 绑定模式、输入、事件与 artifact；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **IR-201**：提供版本化交互适配器接口；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **IR-202**：提供带稳定错误码的会话控制接口；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **IR-203**：统一新会话与重放入口；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。

## 非功能需求

- **NFR-201**：墙钟与客户端不影响确定性结果；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **NFR-202**：故障不得留下半提交状态；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **NFR-203**：默认 loopback、离线且无真实凭据；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。
- **NFR-204**：支持 Windows 且协议不绑定客户端技术；正文见 [`0.2.1 spec §4`](0.2.1-interactive-sandbox/spec.md#4-需求)。

## 成功与退出

- **SC-201**：完成本地手动交易闭环；正文见 [`0.2.1 spec §6`](0.2.1-interactive-sandbox/spec.md#6-成功与验收)。
- **SC-202**：在新进程确定性重放；正文见 [`0.2.1 spec §6`](0.2.1-interactive-sandbox/spec.md#6-成功与验收)。
- **SC-203**：正式研究入口完整拒绝交互产物；正文见 [`0.2.1 spec §6`](0.2.1-interactive-sandbox/spec.md#6-成功与验收)。
- **SC-204**：成果包两次点击内可达且离线可开；正文见 [`0.2.1 spec §6`](0.2.1-interactive-sandbox/spec.md#6-成功与验收)。

版本级需求归属与退出条件由 [`traceability.json`](traceability.json) 唯一拥有。

## 已确认决策

1. H1 是 `engineering-demonstration`，不建立研究声明。
2. 人类输入是外生、可保存、可重放的数据；输入序列属于确定性定义的一部分。
3. 实时调速是现有离散事件内核的运行模式，不是第二套内核。
4. 人类参与者不获得信息特权；其动作与代理订单经过相同市场与风险路径。速度维度不作
   公平性承诺（人类可暂停思考），因此交互运行不得用于速度或信息能力对照。
5. H1 先做单机单人、隔离运行；H2 必须另立规格和预注册协议。

## 待确认事项

- 首个客户端形态、会话启动模板与默认节奏由 0.2.1 的开放问题决定；在这些问题关闭前，
  版本保持 `draft`。
