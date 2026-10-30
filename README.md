# yun-cases

yun 项目测试用例库（test case library of project yun）。

收录可复现的车辆路径与调度算例，用于：

- 功能测试：基本功能测试保证版本符合设计的功能和规则；
- 回归测试：改动求解器后确认已知算例的解不退化；
- 质量对比：当前解与基准已知最优解（BKS）的 gap；
- 性能基准：同一算例上的求解耗时与稳定性。

每个算例是一个自包含的 `.zip` 包（数据表 + 求解参数 + 策略脚本），不依赖外部文件即可导入求解。

## 目录结构

```text
.
├── README.md                       # 本文件：用例库说明与格式约定
└── sintef/                         # 来源：SINTEF 公开基准
    ├── SINTEF_CASES.md             # 算例清单与求解结果记录（Vehicles / Distance / gap）
    └── vrptw/                      # 问题类型：带时间窗车辆路径（VRPTW）
        └── 200customers/           # 规模：200 个客户
            └── c1_2_1.zip          # 单个算例包
└── tests/                          # 测试用例集
```

路径约定为 `<基准来源>/<问题类型>/<规模>/<算例名>.zip`，算例名沿用基准原始编号（如 `c1_2_1`），不做改写。

## 用例包格式

`.zip` 解压后为同名目录，内容分三部分：求解入口、业务数据、费用/标签等可选表。

| 文件 | 说明 |
|------|------|
| `Parameter.yaml` | 求解参数：规划时间范围、策略脚本、装卸策略（本算例 `FILO`）、软约束（如距离权重） |
| `Strategy.lua` | 求解策略：KNN 构造 + ALNS 改进，参数内联在脚本中，便于复现同一求解路径 |
| `Location.csv` | 节点坐标，`Lng`/`Lat` 为平面坐标 |
| `CargoOrder.csv` | 订单：装/卸节点、装/卸时间窗 |
| `CargoSubOrder.csv`、`CargoSubOrderDimensionValue.csv` | 订单拆行及维度取值（如 `weight`） |
| `DistMatrix.csv` | 有向距离/时间矩阵：`Distance` 为整数、`Time` 为秒 |
| `Vehicle.csv`、`VehicleModel.csv` | 可用车辆数、车型、载重与距离计算口径 |
| `Dimension.csv` | 维度定义与精度 |
| `WorkFixed.csv` | 各节点固定作业时长（秒） |
| `WorkEffect.csv`、`WorkCalendar*.csv` | 单位时间处理量、工作日历（本算例为空表，保留 schema） |
| `Charge*.csv`、`Label*.csv`、`Carrier*.csv` | 费用规则、标签、承运商（本算例为空表，保留 schema） |
| `LocationAvailableVehicle.csv`、`DistMatrixCode.csv`、`*LabelValue.csv`、`*DimensionValue.csv` | 附属表：节点可用车辆、矩阵口径、标签与维度取值（本算例多为空表） |

空表只保留表头，用于占住 schema，导入时按空数据处理。

## 功能测试流程
1. 读取[FEATURE_TESTS_CASES.md](feature_tests/FEATURE_TESTS_CASES.md)完成所有功能测试。

## 新增或更新算例

1. 按 `<来源>/<问题类型>/<规模>/<算例名>.zip` 放置，`<算例名>` 与基准编号一致；
2. zip 内只保留数据文件，去掉 `__MACOSX/`、`.DS_Store`、`._*` 等打包残留；
3. 测试用例必须打包上传，不允许多个测试用例放在同一个压缩包；


## 基准来源

- SINTEF TOP（Transportation and Optimization）：<https://www.sintef.no/projectweb/top>
- 其它

## 许可

代码与文档遵循 Apache License 2.0，见 [LICENSE](LICENSE)。算例数据版权归 SINTEF 及原作者所有，引用或再分发时请注明来源。
