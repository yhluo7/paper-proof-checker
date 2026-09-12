# eval：冻结基准与对照实验

本目录存放**先于任何模型运行冻结**的标准答案、打分脚本与对照实验记录。

## 目录内容

| 文件 | 说明 | 是否进入公开仓库 |
|---|---|---|
| `ground-truth.json` | 冻结的标准答案（14 项场景、7 项预埋高风险、3 项映射校验） | 是 |
| `README.md` | 本文件：指标定义与运行方式 | 是 |
| `experiment-2026-09-12.md` | 一次无 Skill / 有 Skill 单次对照的完整记录 | 是 |
| `runs/` | 每次打分的原始产物（`score.json`、原始输出） | 否（本地实验产物） |
| `tmp/` | 实验临时目录 | 否 |

## 冻结原则

`ground-truth.json` 由 `tools/generate_demo.py` 依据 Demo 的**结构与预埋设计**生成，
与任何模型输出无关。生成后不得修改；任何修改都会使既有对照实验失去可比性。

冻结时点与内容规模：

- `scenario_total = 14`、`high_risk_total = 7`、`mapping_checks = 3`
- 生成命令：`python tools/generate_demo.py`
- 校验：`pytest tests/test_demo_benchmark.py -q`

## 指标定义

| 指标 | 计算方式 | 对应 `score.json` 字段 |
|---|---|---|
| 高风险召回率 | 找到的预埋高风险问题数 ÷ 7 | `high_risk_recall` |
| 总体判断准确率 | 判断正确的 14 项 ÷ 14（宽松口径，只看判断） | `verdict_accuracy` |
| 严格口径准确率 | 判断与候选数值 ID 同时正确的比例 | `strict_accuracy` |
| 高风险误报数 | 标准答案中不属于高风险、却被判为高风险的项数 | `high_risk_false_positives` |
| 证据可追溯率 | 可通过验证器定位到段落与页码的判断 ÷ 全部判断 | 见下 |
| 完成率 | 是否在无追加提示的情况下生成正式报告 | 见 `validation_status` |
| 耗时 | 从发送请求到报告完成的时间 | 由记录方填写 |

**证据可追溯率**说明：该指标的分母是模型实际产出的判断数（`produced_total`），
分子是其中通过了验证器回溯检查的条数。验证器通过即意味着每条引用判断都指向了
真实存在的 `paragraph_id` 与页码，每条数值判断都指向了候选列表中的 `number_id`。
因此"验证通过"的运行，其证据可追溯率为 100%；无法产出结构化判断的运行，该指标记为 0%。

## 运行方式

```powershell
# 对一次运行打分（先验证，验证不过则不产生分数）
python tools/score_run.py <run-dir> --label with-skill

# 重新生成 Demo 与冻结标准答案（会覆盖 examples/quick-demo 与 ground-truth.json）
python tools/generate_demo.py
```

结果写入 `eval/runs/<label>/score.json`。同名标签重复打分时自动追加时间戳，
**不覆盖**历史结果——计划文档要求保留全部失败结果，不得挑选最好结果。

## 关于结果的解释边界

- 本目录的记录是**单次案例实验**，不是稳定性评测。样本为 1 次运行、1 个模型、全合成数据。
- 任何"有 Skill 优于无 Skill"的结论都必须在 `experiment-*.md` 中给出原始输出与评分表；
  若对照未显示增益，只公布原始结果，不作优劣宣称。
- 合成数据的表现**不能**代表真实论文上的表现。真实论文的数值更密集、表述更晦涩、参考文献更长。
