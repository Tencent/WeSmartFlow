---
name: state_comparison
label: 状态对比
when_to_use: 概念的核心是"切换不同选项，看结果差异"——如算法对比、函数族对比、A/B 对照、概念辨析（正弦 vs 余弦）
controls: select（切换选项）或 toggle（二选一）; slider（共同参数）; metric（各选项关键指标）; text（当前选项说明）
---

# Pattern: state_comparison（状态对比）

## 适用场景
- 不同算法效果对比（线性搜索 vs 二分搜索）
- 函数族对比（不同参数的同一类函数）
- A/B 对照（有/无某个特性的差异）
- 概念辨析（正弦 vs 余弦、均值 vs 中位数）
- 任何"切换不同选项，看结果差异"的场景

## 推荐控件组合
- **主控件**：`select`（切换选项）或 `toggle`（二选一开关）
- **辅助**：`slider`（调节共同参数）
- **反馈**：`metric`（各选项的关键指标）、`text`（当前选项的说明）

## 代码模板（select 版）

```javascript
// ① 定义各状态的配置
const MODES = {
  linear: {
    label: '线性搜索',
    color: 'danger',
    desc: '逐个比较，最坏 O(n) 次',
    fn: (arr, target) => { /* 返回步骤数组 */ }
  },
  binary: {
    label: '二分搜索',
    color: 'success',
    desc: '每次排除一半，O(log n) 次',
    fn: (arr, target) => { /* 返回步骤数组 */ }
  }
}

// ② 创建控件
const modeSelect = EduViz.select('算法', {
  choices: Object.entries(MODES).map(([v, m]) => ({ value: v, label: m.label })),
  default: 'linear'
})
const targetSlider = EduViz.slider('目标值', { min: 1, max: 20, step: 1, default: 7 })

// ③ 展示元素
const stepsMetric = EduViz.metric('比较次数', { value: '—', color: 'brand' })
const descText = EduViz.text('选择算法查看效果')

// ④ 渲染层
const canvas = EduViz.createCanvas(520, 200)
const ctx = canvas.getContext('2d')

// ⑤ 渲染函数
function update() {
  const mode = MODES[modeSelect.value]
  const c = EduViz.colors()
  // ... 绘制逻辑
  stepsMetric.set('...')
  stepsMetric.setColor(mode.color)
  descText.set(mode.desc)
}

// ⑥ 绑回调
modeSelect.onChange(update)
targetSlider.onChange(update)
EduViz.onThemeChange(() => update())
```

## 代码模板（toggle 版，二选一对比）

```javascript
// 适合"开/关某个特性"的对比
const showTangent = EduViz.toggle('显示切线', { default: false, label: '切线' })
const showSecant = EduViz.toggle('显示割线', { default: true, label: '割线' })

function update() {
  ax.redraw(() => {
    ax.plot(f, { color: 'brand', width: 2 })
    if (showSecant.value) {
      // 画割线
    }
    if (showTangent.value) {
      // 画切线
    }
  })
}

showTangent.onChange(update)
showSecant.onChange(update)
EduViz.onThemeChange(() => update())
```

## 关键注意事项

1. **`select` 的 `choices` 数组顺序就是下拉菜单顺序**，把最常用/默认的放第一个
2. **切换选项时要完整重绘**，不要只更新部分元素（容易残留上一个状态的图形）
3. **用颜色区分不同选项**：每个选项用不同的语义色（`brand`/`success`/`danger`/`warning`）
4. **`metric.setColor()` 跟随当前选项颜色**，让数字和图形颜色一致，增强关联感
5. **`text` 说明当前选项的特点**，不要只显示名称，要说"为什么"

## 完整示例：正弦 vs 余弦 vs 正切

```javascript
const funcSelect = EduViz.select('函数', {
  choices: [
    { value: 'sin', label: 'sin(x)' },
    { value: 'cos', label: 'cos(x)' },
    { value: 'tan', label: 'tan(x)（截断）' }
  ],
  default: 'sin'
})
const freqSlider = EduViz.slider('频率倍数', { min: 0.5, max: 3, step: 0.5, default: 1 })

const FUNCS = {
  sin: { fn: x => Math.sin(x), color: 'brand', desc: '周期 2π，值域 [-1, 1]，从 0 开始' },
  cos: { fn: x => Math.cos(x), color: 'success', desc: '周期 2π，值域 [-1, 1]，从 1 开始' },
  tan: { fn: x => { const v = Math.tan(x); return Math.abs(v) > 5 ? NaN : v }, color: 'warning', desc: '周期 π，在 π/2 处无定义（断开）' }
}

const maxMetric = EduViz.metric('最大值', { value: '1.00', color: 'brand' })
const descText = EduViz.text('')

const canvas = EduViz.createCanvas(520, 280)
const ax = EduViz.axis2d(canvas, { xRange: [-Math.PI * 1.2, Math.PI * 2.5], yRange: [-2, 2] })

function update() {
  const cfg = FUNCS[funcSelect.value]
  const freq = freqSlider.value
  ax.redraw(() => {
    ax.plot(x => cfg.fn(freq * x), { color: cfg.color, width: 2.5 })
  })
  maxMetric.set(funcSelect.value === 'tan' ? '∞' : '1.00')
  maxMetric.setColor(cfg.color)
  descText.set(cfg.desc)
}

funcSelect.onChange(update)
freqSlider.onChange(update)
EduViz.onThemeChange(() => update())
```
