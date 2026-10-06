# 校园提醒与校园网助手（CampusCheckinKit）

一个开源的 Windows 托盘聚合小工具，把两件事合二为一，并且**可以只用其中一件**：

1. **今日校园查寝强提醒** —— 到点弹出全屏强提醒卡片，督促完成查寝/签到。*适用于任何学校*，提醒时间完全自定义。
2. **CUMT 校园网自动登录与保活** —— 自动登录中国矿业大学（CUMT）ePortal 校园网，断网自动重连，并按"明日是否上课"智能识别夜间断网时段。

> **非 CUMT 的同学请注意**：功能 1（强提醒）与校园网无关，任何学校都能直接使用——
> 只需在主菜单把提醒时间改成贵校的查寝/签到时间即可。功能 2 默认对接 CUMT 的
> ePortal 门户，其他学校如需自动登录，可自行修改 `campus_network.py` 中的门户地址。

## 特性一览

- **模块化启用**：主菜单"总览"页可单独开关两个功能模块，只开提醒、只开校园网、或两个都开。
- **首次启动引导**：4 步向导讲清楚强提醒的行为（Esc 关不掉、5 分钟重弹）和校园网登录的用法，并让你选择要启用的模块。
- **主菜单窗口**：默认静默驻留托盘，可从托盘双击/右键打开主菜单；集中进行所有设置、查看状态与关于信息；可切换"启动时自动打开主菜单"。
- **自定义提醒时间**：提醒时间、稍后提醒间隔均可设置，适配所有学校的签到时间。
- **夜间断网智能判断**：CUMT 在**上课日的前一夜**断网（默认 23:30 至次日 07:00）。程序自动拉取中国法定节假日与调休安排推算"明日是否上课"，因此周日到周四夜间会暂停保活，**周五、周六夜间以及假期前一夜网络不断，保活照常工作**；假期结束后的第一个上课日前夜恢复暂停。本地缓存、断网回退到周末规则，断网时段结束自动恢复巡检。
- **节假日跳过签到提醒**（可选）：法定节假日当天不打扰；寒暑假用暂停区间。
- **开机自启检测与引导**：主菜单可一键检测自启是否设置成功（含"指向旧版本"检测）、一键修复，附手动注册表引导；支持发送桌面快捷方式。
- **强提醒机制**：全屏遮罩 + 置顶卡片 + 提示音；未确认关闭 5 分钟后重弹；"已签到/稍后提醒/暂停区间"三种出口。
- **校园网保活**：默认 15 秒巡检（10–60 秒可调）、断网自动连 Wi-Fi 并重登、Windows 解锁/回到桌面立即重登、失败按指数退避重试、断网时段自动暂停与恢复。
- **通知可控**：启动/签到/校园网/调试四类通知，可分别设为系统推送、右下角简洁通知或关闭。
- **隐私**：账号密码只保存在本机 `%APPDATA%\CampusCheckinKit\settings.json`，程序不上传任何数据。

## 安装与运行

### 直接运行（推荐普通用户）

到 [Releases](../../releases) 下载，两种形式任选其一：

| 附件 | 说明 |
|------|------|
| `CampusCheckinKit-v1.0.1-windows.zip` | **推荐**：目录版（onedir），启动快、误报最少；解压后运行 `CampusCheckinKit/CampusCheckinKit.exe`，**不能只拿走 exe**（依赖旁边的 `_internal` 目录） |
| `CampusCheckinKit-v1.0.1.exe` | 单文件版，下载后直接双击运行；启动时需自解压到临时目录，**杀软误报概率明显更高**，且更容易被直接删除 |

两者功能完全一致，均未做代码签名；遇到 Windows SmartScreen 提示时选择"仍要运行"。

> 建议优先使用**目录版（zip）**。单文件版启动时会把自身解压到临时目录再运行，
> 这个"自解压 + 临时目录执行"的动作与恶意软件的投放行为高度相似，是杀软误报的主要来源。

### 被 360 或其他杀软报毒怎么办

本程序没有代码签名证书，而"托盘常驻 + 写开机自启 + 自动登录校园网 + 连接 Wi-Fi"这组行为
在启发式引擎眼里确实很像木马，因此**误报是预期之内的**。请这样处理：

1. **用目录版**，并把整个文件夹放到一个固定位置（例如 `D:\CampusCheckinKit`），不要直接在
   "下载"目录里双击运行——从临时/下载目录运行的无签名 exe 更容易被判为高危并直接删除。
2. 360 弹窗时**不要选"阻止"**，选"允许程序所有操作"，并勾选"加入白名单/信任区"。
   随后进入 360 → 木马查杀 → 信任区 → 添加目录，把整个安装目录加进去；
   只信任 exe 而不信任目录，更新后仍可能被再次拦截。
3. 如果已经被隔离：360 → 木马查杀 → 隔离区 → 恢复并添加信任。
4. 校验下载文件的 SHA-256（见 Releases 页面正文），确认文件未被篡改后再信任。

程序会做的全部"敏感"动作，供你自行核对：

| 行为 | 触发条件 | 说明 |
|------|----------|------|
| 写 `HKCU\...\Run` 开机自启 | 仅当你在主菜单勾选"开机自启" | 只写当前用户，不碰系统启动项，可随时取消 |
| 向学校 ePortal 发 HTTP 登录请求 | 使用校园网登录/保活时 | 目标地址是校园内网门户，账号密码只存本机 |
| `netsh wlan connect` 连接 Wi-Fi | 仅当勾选"重连前先连 Wi-Fi" | 连接你自己保存过的网络 |
| 创建桌面快捷方式 | 仅当你点击按钮 | 调用一次系统 `WScript.Shell` COM 接口 |
| 监听 Windows 解锁事件 | 校园网模块启用时 | 用于解锁后自动重连，不记录任何按键 |

本程序不开启任何端口、不接收外部连接、不上传数据、不修改系统文件。
源码全部公开，欢迎自行审计或本地打包。

### 从源码运行

```powershell
git clone https://github.com/muge-heng/campus-checkin-kit.git
cd campus-checkin-kit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

要求：Windows 10/11、Python 3.10+（使用了 `X | Y` 类型语法）、PySide6。

### 打包为 exe

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean CampusCheckinKit.spec            # 目录版（推荐）
pyinstaller --noconfirm --clean CampusCheckinKit-onefile.spec    # 单文件版
```

目录版产物在 `dist\CampusCheckinKit\`，onedir + 不压缩 UPX，启动更快、误报更少。
单文件版产物为 `dist\CampusCheckinKit.exe`，可独立分发，但首次启动需自解压、误报风险相对更高。

> 注意：直接用 `pyinstaller --onefile app.py` 这类命令行方式打包会**覆盖 `CampusCheckinKit.spec`**，
> 因此仓库把两种构建分别固定为两个 spec 文件。

## 使用说明

### 首次启动

程序会弹出引导：选择启用的模块 → 了解强提醒机制 → 了解校园网登录用法 → 设置开机自启。
之后可随时在主菜单"总览"页底部"重置首次引导"重看。

### 今日校园提醒（所有学校可用）

1. 主菜单 → "提醒设置"，把每日提醒时间改成贵校查寝/签到时间（默认 21:00）。
2. 到点后全屏弹出提醒卡片：
   - **已签到**：今天不再提醒；
   - **稍后提醒**：N 分钟后再弹（默认 10 分钟）；
   - **暂停区间**：设置寒暑假等日期区间，区间内不提醒；
   - 直接关掉弹窗不确认？5 分钟后重新强弹，Esc 无法关闭——这是刻意的。
3. 可勾选"法定节假日自动跳过"（自动拉取节假日与调休，含周末可选）。
4. "预览提醒"按钮不会修改任何真实状态，可先看看效果。

### CUMT 校园网自动登录与保活

1. 主菜单 → "校园网"，填写校园网账号（学号）、密码，选择运营商，保存后点"立即登录"验证。
2. 按需勾选：
   - **启动后自动登录**；
   - **断网后自动检测并重连**（保活，默认 15 秒巡检）；
   - **重连前先连指定 Wi-Fi**（默认 `CUMT_Stu`）；
   - **智能判断夜间断网**：只在真会断网的时段（明日上课的前一夜）暂停保活，其余夜间照常守护；
   - **夜间失败过多暂停重连**：连续失败时指数退避，避免重试风暴；
3. Windows 解锁或回到桌面后会自动尝试登录一次。
4. 其他学校：在 `campus_network.py` 修改 `EPORTAL_LOGIN_URL_BASE` 与登录参数即可复用整套保活逻辑。

### 开机自启与快捷方式

主菜单 → "启动与快捷方式"：勾选即写入当前用户注册表 Run 项；"立即检测自启状态"
会验证注册表项是否存在、是否指向当前正在运行的这个程序（改过存放路径后尤其有用）；
失败时提供手动注册表引导，并可一键"发送快捷方式到桌面"。

## 配置文件

`%APPDATA%\CampusCheckinKit\settings.json`（节假日缓存在同目录 `cache\holidays.json`）。

主要字段：

| 字段 | 说明 |
|------|------|
| `enable_reminder` / `enable_network` | 两个功能模块的总开关 |
| `start_with_main_window` | 启动时是否自动打开主菜单（默认静默到托盘） |
| `remind_time` / `snooze_minutes` | 每日提醒时间 / 稍后提醒间隔 |
| `skip_holidays` / `skip_weekends` | 节假日、周末自动跳过提醒 |
| `pause_ranges` | 暂停日期区间（寒暑假） |
| `network_login_enabled` | 校园网登录功能实际开关（还要求 `enable_network` 为真） |
| `network_username` / `network_password` / `network_isp` | 账号、密码、运营商 |
| `network_auto_login` / `network_keep_alive` | 启动自动登录 / 断网保活 |
| `network_auto_wifi` / `network_wifi_ssid` | 重连前先连 Wi-Fi / SSID（默认 CUMT_Stu） |
| `network_night_mode` / `network_probe_interval_seconds` | 失败退避暂停 / 巡检间隔（10–60 秒） |
| `network_smart_night_cut` | 是否按"明日是否上课"智能判断夜间断网时段 |
| `network_cut_start_time` / `network_cut_end_time` | 断网窗口，默认 `23:30` 至次日 `07:00`（其他学校可改成贵校时刻） |
| `notification_*` | 各类通知方式：`system` / `toast` / `none` |
| `onboarding_completed` / `quiet_start` | 引导是否完成 / 静默启动 |

调试字段：`last_ack_date`（今日已确认）、`last_reminded_date`（今日已提醒，清空可恢复未提醒状态）。

## 文件结构

```
campus-checkin-kit/
├── app.py                          # 主程序入口（托盘 + 调度）
├── main_window.py                  # 主菜单窗口（总览/提醒/校园网/启动/通知/节假日/关于）
├── onboarding.py                   # 首次启动引导向导
├── reminder_dialog.py              # 强提醒弹窗与暂停区间对话框
├── campus_network.py               # 校园网 ePortal 登录 / Wi-Fi / 保活策略
├── holiday_service.py              # 法定节假日拉取、缓存与回退
├── network_dialog.py               # 校园网配置对话框
├── notification_manager.py         # 通知管理器（系统推送/简洁通知/关闭）
├── notification_settings_dialog.py # 通知设置对话框
├── toast_notification.py           # 右下角简洁通知组件
├── windows_session_monitor.py      # Windows 解锁/回到桌面监听
├── settings_store.py               # 配置存储
├── CampusCheckinKit.spec           # PyInstaller 打包配置（目录版，推荐）
├── CampusCheckinKit-onefile.spec   # PyInstaller 打包配置（单文件版）
└── assets/today-campus.png         # 托盘/弹窗图标（可替换）
```

## 免责声明

- 本工具为个人开源学习用途，与"今日校园"APP、中国矿业大学官方均无隶属关系。
- 校园网登录仅向你所在学校的 ePortal 门户发起你自己账号的常规登录请求；请遵守所在学校的网络使用规定。
- 节假日数据来自公共 API（timor.tech），仅供判断参考，重要日程请自行核对。

## License

[MIT](LICENSE)
