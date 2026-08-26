# 这些河现在只是候选名单

`configs/network_catalog_v1.yaml` 先按公开目录改过一版，不是已经打完分的数据集。

全国 USGS NWIS 日均水温目录：3995 条序列，跨度至少八年的 1648 条。按河名和分区归组后，至少四站且目录同期够八年的有 31 条。

- **已经用过的**：金沙江、Chattahoochee。不能再当最后检验。Chattahoochee 目录上有 8 站，但共同窗口只有大约 5 年。
- **用来定方法的**：Delaware、Willamette、Suwannee、Yellowstone、Rio Grande、Madison、Cahaba、McKenzie。
- **用来锁设定的**：Mahoning、Roanoke、Santa Fe、Clearwater。
- **留到最后看的**：科罗拉多大峡谷、Columbia、卢瓦尔、瑞士阿勒-莱茵、Ohio、Deschutes。只记目录，不下载水温。科罗拉多和 Columbia 目录上有站，但对齐后没有八年共同窗口。

卢瓦尔：Hub'Eau 河名就是卢瓦尔的 11 站；目录没有起止年。  
瑞士：公开站名 246 个，历史日均要向 FOEN 订。

Sacramento、Connecticut、Potomac、Tennessee、South Platte 原先猜的站号同期不够，已从定方法名单里拿掉。不是再猜三个站就能补上。

脚本：`python scripts/49_national_temperature_catalog.py`  
结论：`results/framework/public_catalog/feasibility_decision.md`
