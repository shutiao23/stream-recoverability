# 实现核对所用的一手资料

- MOVE.1 的定义及其与回归、加噪回归的区别：[Hirsch 1982](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/WR018i004p01081)；日流量应用和年峰值方法差异见 [USACE 官方说明](https://www.hec.usace.army.mil/confluence/sspdocs/ssptutorialsguides/daily-flow-record-extension/daily-flow-record-extension-with-move-1)。本项目的 H30 增补是敏感性基线，不称 Bulletin 17C 推荐的年峰值方法。
- 区间资料和期望矩算法：[USGS Bulletin 17C](https://pubs.usgs.gov/publication/tm4B5)。已知观测高于一个下界属于响应的右删失，见 [USACE EMA 指南](https://www.hec.usace.army.mil/confluence/sspdocs/ssptutorialsguides/expected-moments-algorithm-study-guide/overview)。本项目采用 Gaussian 趋势工作似然，没有把它命名成 EMA。
- 地区间校准异质性及预测区间：[Riley 等 2016](https://www.bmj.com/content/353/bmj.i3140)。项目报告独立组方差和交换性限制，随机效应区间不称严格风险保证。
- SAITS 与 CSDI 的接口：[PyPOTS 官方文档](https://docs.pypots.com/en/dev/pypots.imputation.html)，并核对本机 PyPOTS 1.5 源码。`CSDI.predict(..., n_sampling_times=20)` 保留抽样维；公开构造器支持 `mix`/`random`，本项目使用 `mix` 配连续水温缺口模板。
- 正式条件覆盖：[Gibbs、Cherian 和 Candès 2025](https://academic.oup.com/jrsssb/article/87/4/1100/8058684)及[作者代码](https://github.com/jjcherian/conditional-conformal)。最终使用 0.0.4 的有限基二分类 LAC 对照，同时评估保守和逐病例独立随机化版；等价边界线性规划与作者实现做了数值对照。
- 正式半监督风险控制：[Einbinder、Ringel 和 Romano 的版本 2](https://arxiv.org/html/2412.11174v2)。本项目应用一般损失算法 1 和有限样本 WSR 算法 4，以独立连通组为单位，保持标签、无标签校准、测试集合互斥；不是给旧正态 PPI 诊断改名。
- 原始全国纯日期阶段：[USGS 元数据和 API 文档](https://api.waterdata.usgs.gov/docs/ogcapi/)及[配额说明](https://api.waterdata.usgs.gov/docs/ogcapi/keys/)。当时只请求日期和审批字段，保存原始请求及续页位置，并遵守实际 `Retry-After`；这些原始文件保留，后续数值阶段另记。
- 全国数值阶段：[USGS 高效查询说明](https://api.waterdata.usgs.gov/docs/ogcapi/efficiency/)与[迁移指南](https://api.waterdata.usgs.gov/docs/ogcapi/migration/)。纯日期原始缓存保留；后续全国 H30 源域采集包含水温，不再称纯日期或盲检验。每页 50,000 条并保护旧版 10,000 条分页，保留实际限流时间。未调用新西兰候选的河温接口。
- POWER 时间与原生分辨率：[NASA 日接口说明](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)及[官方多点请求指南](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/)。日值默认 LST；气象原生网格按 0.5°×0.625° 复用，不把它当作实测气象站。
- 邻近观测气温：[NOAA GHCN-Daily 官方说明](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt)、[数据集 DOI](https://doi.org/10.7289/V5D21VHZ)与[Menne 等的方法论文](https://doi.org/10.1175/JTECH-D-11-00103.1)。按坐标和 TAVG 记录范围选最近站，不按水温误差选；非空 QFLAG 排除，值为摄氏十分位。Source S 日平均截至 2400 UTC，其他来源约定不一，保留原日期并声明与 POWER LST 的时钟混杂。它不是河岸完美气温真值。
- 高分辨率气温：[Daymet 官方获取说明](https://daymet.ornl.gov/getdata)及 [REST 接口](https://daymet.ornl.gov/web_services.html)。请求只涉及已打开站点的外部驱动；保存原 CSV 与完整请求 URL。以 `(tmin+tmax)/2` 比较 POWER 日均值时，空间分辨率与聚合定义同时变化，不能单独归因给网格大小。
- 驱动资料引用：[Thornton 等 2021 的 Daymet V4 论文](https://www.nature.com/articles/s41597-021-00973-0)、[Muñoz-Sabater 等 2021 的 ERA5-Land 论文](https://essd.copernicus.org/articles/13/4349/2021/)及 [Open-Meteo 历史 API 官方说明](https://open-meteo.com/en/docs/historical-weather-api)。本项目明确请求 `models=era5_land` 与 UTC 日均温，未用服务默认的多模型拼接选项；原请求和配额错误保留。
- 新区域元数据：[Horizons 官方 Hilltop 服务](https://envirodata.horizons.govt.nz/api/hilltop/data)及[机构维护的 WHURL](https://github.com/HorizonsRC/whurl)解释目录、测量、时间范围和观测接口。此次仅请求 SiteList/MeasurementList/TimeRange/SiteInfo/CollectionList，未请求新河温。Horizons 58 个候选的当前公开档案不足四个完整热年时间支持，转查 Greater Wellington 元数据。档案入口的出处包括[新西兰环境部的资料质量调查](https://environment.govt.nz/assets/publications/Freshwater/stocktake-of-data-quality-code-and-metadata-usage-in-regional-council-water-quality-datasets.pdf)。
- 新西兰原生日期：[NEMS 河温标准](https://www.lawa.org.nz/media/16588/nems-water-temperature-recording-2013-06-2-.pdf)要求记录用 NZST；[NEMS 术语表](https://www.lawa.org.nz/media/2982084/NEMS-Glossary.pdf)定义其为固定 UTC+12。机构真实序列时钟和质量码仍须核定；没有以夏令时城市时区代替标准时间。已处理报告序列的 0.5°C 恢复容差也不是传感器无误差的证明。
- 公开注册：[OSF 官方注册说明](https://help.osf.io/article/330-welcome-to-registrations)、[API 文档](https://developer.osf.io/)及[官方日期序列化源码](https://github.com/CenterForOpenScience/osf.io/blob/develop/api/base/serializers.py)。固定 API 2.20 获取带明确时区的登记时间；核对 registration 的存档附件字节，而不是可编辑原项目的同名文件。本地草稿、附件包和文件时间不能代替已接受的公开平台记录。

完整文献背景及 120 条条目仍以原 [审稿意见参考文献](../wrr_mit_style_review_20261023/REVIEW_ZH.md)为准；新增论文引用位于 `paper/wrr_tr/references_review_completion.bib`。上述核对不构成重新声称本轮逐条在线审计了全部 120 条文献。
## 补充核实：法国源站坐标（2026-10-24）

此前九个 Hub’Eau 源站未出现在既有 v18 坐标表中。已按原八位站号查询[机构温度站点目录](https://hubeau.eaufrance.fr/api/v1/temperature/station)，九站均返回地理坐标；其经纬度与 CRS84 Point 几何坐标及既有全站目录一致。这里没有请求河温观测。原始响应、请求地址、SHA256 与逐站连接保存在 `inputs/hubeau_coordinate_metadata/` 和 `inputs/source_coordinate_supplement_audit.json`；`513_review_completion_source_coordinates.py` 可复核。


## 湖泊出口的明确机构标注

[USGS 14158500 官方站点资料](https://waterdata.usgs.gov/monitoring-location/USGS-14158500/)明确将该站标为 Clear Lake 出口。与已缓存 USGS 站点名称一致，元数据网页及 SHA256 保存在 `inputs/lake_outlet_metadata/`。失败地图仅将此站记为机构明确标注的出口；其他站保持未知，不因站名含 lake 或靠近湖泊推断分类。一个站的结果不支持河流类型的普遍效应或热惯性因果解释。
