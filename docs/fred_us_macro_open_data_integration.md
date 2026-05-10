# FRED US Macro Open Data Integration

## 定位

`fred_us_macro_open_data` 是 `News Event Hub` 的美国宏观结构化事件补充源。

它不是普通新闻 feed，也不是日报项目私有数据源。它的合理位置是：

- `fact lane`
- `coverage_scope = macro`
- `event_type = macro_data`
- `action_key = macro_release`

上游仓库：

- https://github.com/superpilot69/fred-us-macro-open-data

## 为什么接入

这个数据集把 FRED 的美国核心宏观序列整理成 replay-ready event，并附带部分 Investing.com economic calendar 的 actual / forecast / previous / surprise 字段。

对共享层的价值：

- 给宏观事件提供结构化 release timestamp，而不是只依赖新闻标题
- 给 CPI / PCE / 非农 / 初请 / GDP / 零售销售 / Fed decision 等事件提供 surprise 维度
- 给雷达系统提供公司与行业异动旁边的宏观背景层
- 给后续 ranking 回测提供历史宏观事件锚点

## Runtime 边界

repo 内只保留：

- source registry 条目
- importer 脚本
- integration 文档
- smoke test

不要把上游 `data/fred-us-macro-events.json`、`fred-us-macro-history.json` 或 consensus JSON 提交进本仓库。

运行时下载缓存默认放在：

```bash
runtime/fred_us_macro_open_data/
```

该目录受 `.gitignore` 保护。

## 稳定入口

按默认近 400 天窗口导入：

```bash
python3 scripts/import_fred_us_macro_open_data.py --db runtime/news_event.db
```

导入完整历史：

```bash
python3 scripts/import_fred_us_macro_open_data.py --db runtime/news_event.db --lookback-days 0
```

导入后沿用现有 Layer 2 / Layer 3：

```bash
python3 scripts/build_event_layer.py --db runtime/news_event.db
python3 scripts/export_consumer_views.py --db runtime/news_event.db
```

部署到 `private runtime`：

```bash
scripts/deploy_runtime_fred_macro_import.sh
```

该部署脚本会安装：

- `unified-news-fred-macro-import.service`
- `unified-news-fred-macro-import.timer`

timer 当前按 `OnUnitActiveSec=12h` 执行。importer 成功后触发 `unified-news-event-layer.service`，再沿用 event layer 已有的 consumer views 派生链路。

## 写入方式

当前 v1 不新增专表。importer 会把上游宏观事件合成结构化 `news_articles` 行：

- `source_id = fred_us_macro_open_data`
- `published_at = upstream createdAt`
- `timestamp_quality = exact | estimated`
- `title = textZh / textEn`
- `summary = release + series + consensus 摘要`
- `body_text = JSON`

`body_text` JSON 会保留：

- upstream event id
- dataset generated timestamp
- releaseDateApproximate
- full upstream event payload
- consensus actual / forecast / previous / surprise

Layer 2 builder 再把这些 article 转成 `macro_data` event，并映射到 `通胀`、`美国就业`、`美国增长`、`美联储` 等 macro theme。

## 注意事项

- 上游 repo 很新，正式生产化前仍要观察更新稳定性。
- FRED 是 observation / release-date source of record；Investing.com consensus 字段只作为 enriched context 使用。
- `releaseDateApproximate = true` 的历史事件不能当作精确分钟级事件时点。
- 这个源不替代 Reuters / Fed press / 财经快讯；它提供结构化宏观日历事实和 surprise context。
