# 从 YAML 迁移到 H3C TV Control 插件

## 前提

- Home Assistant 已能访问 H3C S5550 交换机（Telnet 23 端口）
- 现有 YAML 方案（`packages/tv_internet/tv_internet.yaml`）已验证 ACL 控制正常

## 1. 安装插件

将 `custom_components/h3c_tv_control/` 目录复制到 Home Assistant 配置目录：

```bash
cp -r custom_components/h3c_tv_control /config/custom_components/
```

重启 Home Assistant。

## 2. 添加集成

1. 进入 **设置 → 设备与服务 → 添加集成**
2. 搜索 **H3C TV Control**
3. 填写交换机信息：
   - IP: `192.168.1.254`
   - 用户名: `hass_robot`
   - 密码: 你的交换机密码
   - 端口: `23`
   - ACL ID: `3000`
4. 提交后集成会自动测试连接并创建实体

## 3. 绑定电视实体

1. 在 **设置 → 设备与服务** 中打开 **H3C TV Control**
2. 点击 **配置**
3. 为主卧、客厅、老人房和书房选择对应的 `media_player` 实体
4. 未绑定的电视仍可控制 ACL，但不会累计使用时间

## 4. 验证新实体

集成会创建约 40 个实体（4 台电视 × 10 个实体）：

| 实体 | 说明 |
|------|------|
| `switch.*_internet` | 电视上网开关 |
| `switch.*_child` | 儿童控制开关 |
| `number.*_session_minutes` | 单次允许分钟 |
| `number.*_daily_minutes` | 每日允许分钟 |
| `number.*_cooldown_minutes` | 冷却时间 |
| `select.*_allowed_window` | 允许时段 |
| `sensor.*_daily_used` | 今日已用分钟 |
| `sensor.*_session_remaining` | 本次剩余分钟 |
| `sensor.*_cooldown_remaining` | 冷却剩余分钟 |
| `button.*_daily_reset` | 今日初始化 |

在 **开发者工具 → 状态** 中搜索 `h3c_tv_control` 确认实体已创建。

测试：
- 手动开/关电视上网开关
- 开启儿童控制，设置时间段和时长限制
- 等待轮询（默认 60 秒）确认状态校正

## 5. 停用旧 YAML

确认插件工作正常后：

1. 重命名或删除旧 package：

```bash
mv /config/packages/tv_internet/tv_internet.yaml \
   /config/packages/tv_internet/tv_internet.yaml.disabled
```

2. 在 HA 中删除旧实体（可选）：
   - `sensor.sony_tv_internet_status`
   - 旧的 `switch.*电视上网` template switch

3. 重新加载 YAML 或重启 Home Assistant

## 6. 更新仪表盘

将仪表盘卡片中的实体 ID 替换为新插件实体。参考 [dashboard_example.yaml](dashboard_example.yaml)。

旧实体示例：

```yaml
entity: switch.ke_ting_dian_shi_shang_wang
```

新实体示例（entity_id 因配置而异，以开发者工具中实际 ID 为准）：

```yaml
entity: switch.living_room_internet
```

## 6. 回滚

如需回滚到 YAML 方案：

1. 在 HA 中删除 H3C TV Control 集成
2. 恢复 `tv_internet.yaml.disabled` 为 `tv_internet.yaml`
3. 重启 Home Assistant

## 7. 与旧脚本的关系

插件内置了 `h3c_client.py`，功能等同于 `scripts/tv_internet/tv_internet_control.py`。迁移后：

- 插件不依赖 `H3C_SWITCH_PASSWORD` 环境变量（密码存在 config entry 中）
- 旧脚本可保留作为命令行调试工具
- `shell_command` 和 `command_line` sensor 不再需要
