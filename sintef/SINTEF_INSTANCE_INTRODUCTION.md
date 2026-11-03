# SINTEF用例集

> SINTEF地址: https://www.sintef.no/projectweb/top

## VRPTW

因为优化目标优先考虑最少的用车，其次考虑最小化总距离。于是所有`instance`建模设置极大的`cost constraint`固定成本=`100000`,
次目标设置`distance soft constraint`其距离系数为`0.001`。

项目`yun`对比`BKS`的登记表见 [SINTER_VRPTW_INSTANCE.csv](SINTER_VRPTW_INSTANCE.csv)

其中，表字段如下：

| 字段            | 说明                                              | 示例      |
|---------------|-------------------------------------------------|---------|
| `Instance`    | 实例                                              | c1_2_1  |
| `BksVehicle`  | 已知最优的车辆数                                        | 20      |
| `BksDistance` | 已知最优的总距离                                        | 2704.57 |
| `YunVehicle`  | Yun得到最优的车辆数                                     | 20      |
| `YunDistance` | Yun得到最优的总距离                                     | 2704.57 |
| `GapVehicle`  | `YunVehicle`-`BksVehicle`                       | 0       |
| `GapDistance` | \|`YunDistance`-`BksDistance`\| / `BksDistance` | 0.000   |
