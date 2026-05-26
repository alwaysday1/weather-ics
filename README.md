# weather-ics

苹果日历 / Google Calendar / Outlook 通用天气订阅。数据源 [Open-Meteo](https://open-meteo.com)，免费、无需 API key，CC BY 4.0。

## 一次性体验

```bash
python3 weather_ics.py --city shanghai
# → 生成 shanghai_weather.ics，AirDrop 到 iPhone 即可订阅
```

预设城市：`shanghai` `beijing` `shenzhen` `hangzhou` `singapore`。
任意坐标：`--lat 31.23 --lon 121.47 --name "上海"`。

## 持续部署（推荐）

GitHub Actions 每 6 小时跑一次，结果发布到 GitHub Pages，订阅 URL 永久不变。

1. 新建一个 repo，把 `weather_ics.py` 和 `.github/workflows/refresh.yml` 提交进去。
2. Settings → Pages → Source 选 **GitHub Actions**。
3. Actions 页面手动跑一次 *Refresh weather ICS* 确认绿灯。
4. 苹果日历 → 文件 → 新建日历订阅 → 填：
   ```
   https://<user>.github.io/<repo>/shanghai.ics
   ```
   自动刷新频率建议 *每小时* 或 *每天*（系统会缓存，不会每次都拉源站）。

## 输出格式

每天一个 all-day VEVENT。标题示例：

```
☀️ 晴 27°/18°
🌧 小雨 22°/18° 🌧85%
⛈ 雷阵雨 27°/19° 🌧70%
```

描述里附气温区间、降水概率、累计降水、最大风速、日出日落。

UID 按 `weather-<city>-<yyyymmdd>` 生成，**重复订阅会覆盖而不是堆积**——同一天的预报每次刷新都覆盖前一次结果，符合日历客户端预期。

## 配额

Open-Meteo 非商用 10,000 次/天免费。本方案一天最多 4 次刷新 × 几个城市，远低于上限。

## 自定义

- 想要小时级预报：把 `daily=...` 换成 `hourly=...`，每小时一个 VEVENT，但 16 天 × 24 = 384 个事件会让日历视图变拥挤，一般不推荐。
- 想要 7 天而不是 16：`--days 7`。
- 自部署 Open-Meteo（无配额、空气隔离环境）：参考其 GitHub，Docker 一行启动。
