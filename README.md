# weather-ics

苹果日历 / Google Calendar / Outlook 通用天气订阅。

- 天气预报：[Open-Meteo](https://open-meteo.com)，免费、无需 API key，CC BY 4.0。
- 上海气象预警：[中国气象局](https://weather.cma.cn/) / 国家预警信息发布中心，无需 API key。

## 一次性体验

```bash
python3 weather_ics.py --city shanghai
# → 生成 shanghai_weather.ics，包含天气预报和上海当前官方预警
```

预设城市：`shanghai` `beijing` `shenzhen` `hangzhou` `singapore`。
任意坐标：`--lat 31.23 --lon 121.47 --name "上海"`。

## 上海官方预警

`shanghai` 预设会自动读取当前生效的上海市、中心城区和各区气象预警，包括台风、暴雨、大风、雷电、高温、大雾等中国气象局接口返回的信号。日历中显示为单独的限时事件，例如：

```
🟡 上海大风黄色预警
🚨 上海台风红色预警
```

同一种信号的市级和区级预警会合并成一条事件，标题采用其中最高级别，描述保留覆盖区域、官方原文和详情链接，避免十几个区同时发布时刷屏。同一天预警升级时 UID 不变，日历客户端会更新原事件。

```bash
# 上海预设：自动尝试读取预警；接口临时不可用时仍生成天气预报
python3 weather_ics.py --city shanghai --alerts auto

# 严格模式：预警接口不可用时直接失败
python3 weather_ics.py --city shanghai --alerts cma

# 仅生成天气预报
python3 weather_ics.py --city shanghai --alerts none

# 自定义坐标若要附加上海预警，需要显式指定行政区划代码
python3 weather_ics.py --lat 31.23 --lon 121.47 --name 上海 --alerts cma --alert-adcode 31
```

> 注意：日历订阅不是应急推送渠道。生成任务和日历客户端都可能延迟刷新；中国气象局公开 Web 数据接口也没有稳定性 SLA。接口不提供明确解除时间，事件结束时间会按预警原文的“未来 N 小时”推算，实际状态始终以官方详情页或权威预警 App / 短信为准。

## 持续部署（推荐）

GitHub Actions 每小时跑一次，结果发布到 GitHub Pages，订阅 URL 永久不变。
工作流会重试 Open-Meteo 和中国气象局的瞬时网络故障；如果 CMA
预警接口在重试后仍不可用，会输出 warning 并发布仅含天气预报的日历。
Open-Meteo 在重试后仍不可用时任务才会失败并发送 GitHub 通知。

1. 新建一个 repo，把 `weather_ics.py` 和 `.github/workflows/main.yml` 提交进去。
2. Settings → Pages → Source 选 **GitHub Actions**。
3. Actions 页面手动跑一次 *Refresh weather ICS* 确认绿灯。
4. 苹果日历 → 文件 → 新建日历订阅 → 填：
   ```
   https://<user>.github.io/<repo>/shanghai.ics
   ```
   自动刷新频率建议设为 *每小时*（系统仍可能缓存或延迟拉取）。

## 输出格式

每天一个全天气象预报事件。标题示例：

```
☀️ 晴 27°/18°
🌧 小雨 22°/18° 🌧85%
⛈ 雷阵雨 27°/19° 🌧70%
```

天气事件描述里附气温区间、降水概率、累计降水、最大风速、日出日落；预警事件附官方原文、覆盖区域和详情链接。

UID 按 `weather-<city>-<yyyymmdd>` 生成，**重复订阅会覆盖而不是堆积**——同一天的预报每次刷新都覆盖前一次结果，符合日历客户端预期。

## 配额

Open-Meteo 非商用 10,000 次/天免费。本方案每小时刷新一次，即每个城市最多 24 次/天，仍远低于上限。

## 定时任务保活

GitHub 会自动停用长期无仓库活动的公开仓库定时工作流。`.github/workflows/heartbeat.yml` 每月更新一次 `.github/heartbeat.md` 并提交到 `main`，避免天气刷新任务因 60 天无活动而停用。该工作流只申请 `contents: write` 权限；如果同月重复运行，内容不变且不会产生新提交。

## 自定义

- 想要小时级预报：把 `daily=...` 换成 `hourly=...`，每小时一个 VEVENT，但 16 天 × 24 = 384 个事件会让日历视图变拥挤，一般不推荐。
- 想要 7 天而不是 16：`--days 7`。
- 自部署 Open-Meteo（无配额、空气隔离环境）：参考其 GitHub，Docker 一行启动。
