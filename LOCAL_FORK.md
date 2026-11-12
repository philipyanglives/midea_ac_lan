# 310A1394 冰箱制冰功能本地 fork

基于 `wuwentao/midea_ac_lan` `v2026.10.0`，集成版本标为 `2026.10.1`。仅对型号 `310A1394`、子类型 `56` 增加制冰功能；依赖仍是官方 `midea-lan==2026.10.0`，协议适配代码位于 `custom_components/midea_ac_lan/ca_ice.py`。

## 实体

| 功能 | 实体键 | 类型 | 默认创建 |
|---|---|---|---|
| 正在制冰 | `iced_mode` | 二元传感器 | 是 |
| 出冰口状态 | `ice_mouth_power` | 二元传感器 | 是 |
| 制冰水盒状态位 | `freezing_ice_machine_water_status` | 二元传感器 | 是 |
| 冰盒状态位 | `freezing_all_ice_status` | 二元传感器 | 是 |
| 制冰机电源 | `freezing_ice_machine_power` | 开关 | 否，需在冰箱选项中启用 |

冰盒与水盒的状态位只按协议 `0/1` 暴露。旧文档将其解释为“冰满/缺冰”“水满/缺水”，但上游 Lua 只标为 `valid/invalid`；需与冰箱面板和美居 App 实际状态对照后才能确定含义。此 fork 不实现“快速制冰/普通制冰”模式。

## 控制边界

- 仅目标型号允许制冰电源写入；其他冰箱保持原行为。
- 必须在最近 120 秒内收到完整冰箱状态，才组装控制报文；只改变制冰电源位，并保留其它控制字段。不乐观更新开关，等待冰箱回报状态。
- 已在隔离的 HA Core Python 3.14 环境验证解析、报文编码和型号限制；新增 6 项测试通过。另一个底层库 fork 的 CA 测试 82 项通过。尚未向实际冰箱发送控制命令。
- 原集成仓库在现用 Core 环境下有 19 项 `test_midea_entity.py` 夹具失败；上游原标签同样出现完全相同的 19 项失败，与本 fork 改动无关。

## 安装与回滚

安装前需完成 HA 配置备份、保存现有 `/config/custom_components/midea_ac_lan/`，并确认所有美的配置条目正常。将本 fork 的 `custom_components/midea_ac_lan/` 替换到 HA `/config/custom_components/midea_ac_lan/` 后检查配置，再重启 Core；确认其它美的设备仍正常，最后在冰箱的集成选项中启用制冰电源开关。HACS 自动更新可能覆盖本地 fork，部署后需将更新来源切换到 fork 或暂缓此集成的自动更新。

回滚时恢复备份的原集成目录并重启 Core；新增实体会消失，原有实体 ID 与配置条目不变。实际安装、重启和制冰控制测试尚未执行。

对应的底层库改动位于本机 `/Volumes/MacData/Users/philip/Dev/Projects/midea-lan-ice/`，用于后续向上游按库层架构提交，不是本地安装的必要条件。
