# H3C S5550 Home Assistant TV Control

这个项目用于在 Home Assistant 中控制多台 Sony 电视是否允许访问互联网，并提供儿童上网时间管理。

核心思路是：Home Assistant 通过自定义集成 `h3c_tv_control` 登录 H3C S5550 交换机，修改指定 ACL 规则，从而允许或禁止对应电视上网。

## 功能

### 电视上网控制

- 在 Home Assistant 中显示 4 台电视的上网开关（原生 Switch 实体，标准滑块 UI）
- 开启开关时，删除对应电视的 deny ACL 规则，允许上网
- 关闭开关时，恢复对应电视的 deny ACL 规则，禁止上网
- 通过 DataUpdateCoordinator 每 60 秒轮询交换机 ACL，校正真实状态

### 儿童管理

- 每台电视可单独启用儿童控制
- 可绑定 HA 中对应的 `media_player`，按电视真实开关机状态计时
- 单次使用时长限制（默认 30 分钟）
- 每日总时长限制（默认 90 分钟）
- 单次用满后的冷却时间（默认 60 分钟）
- 允许时段预设：全天、白天 08:00–20:00、晚上 20:00–08:00
- 单次、每日或时段条件到期时自动断网
- 冷却结束、允许时段开始或每日 0 点重置后自动恢复上网

## 安装

1. 将 `custom_components/h3c_tv_control/` 复制到 `/config/custom_components/`
2. 重启 Home Assistant
3. 设置 → 设备与服务 → 添加集成 → 搜索 **H3C TV Control**
4. 填写交换机 IP、用户名、密码
5. 在集成“配置”中，为每台电视选择对应的 `media_player` 实体

详细迁移步骤见 [docs/h3c_integration_migration.md](docs/h3c_integration_migration.md)。

## 主要文件

| 路径 | 说明 |
|------|------|
| `custom_components/h3c_tv_control/` | Home Assistant 自定义集成 |
| `packages/tv_internet/tv_internet.yaml` | 旧 YAML 方案（可被插件替代） |
| `scripts/tv_internet/tv_internet_control.py` | 命令行调试脚本 |
| `docs/h3c_integration_requirements.md` | 插件需求文档 |
| `docs/h3c_integration_migration.md` | YAML 迁移指南 |
| `docs/dashboard_example.yaml` | 仪表盘配置示例 |
| `docs/tv_internet.md` | 原始部署与调试说明 |

## 仪表盘

参考 [docs/dashboard_example.yaml](docs/dashboard_example.yaml)，使用 `type: entities` 卡片显示标准滑块开关。

## 将来发展

- 科学上网路由器出口切换
- 动态路由状态监控
- 每日开启次数限制
- 家长密码 / 临时加时

## 注意

- 插件通过 Config Flow 配置交换机密码，不写入代码
- 旧 YAML 方案使用 `H3C_SWITCH_PASSWORD` 环境变量，迁移后不再需要
- 旧脚本 `tv_internet_control.py` 可保留作为命令行调试工具
