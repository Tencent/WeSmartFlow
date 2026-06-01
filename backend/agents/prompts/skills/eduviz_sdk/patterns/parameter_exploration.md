---
name: parameter_exploration
label: 参数探索
when_to_use: 概念的核心是"改变某个参数，观察结果如何变化"——如函数图像、概率分布、物理公式、几何变换
controls: slider × 1~3（主参数）; toggle（辅助线开关）; select（切换函数类型）; metric（关键数值）; latex（公式实时更新）
---

# Pattern: parameter_exploration（参数探索）

## 适用场景
- 数学函数图像（改变参数看曲线变化）
- 概率分布（调节均值/方差）
- 几何变换（旋转角、缩放比）
- 物理公式（改变初速度/角度看轨迹）
- 任何"拖动滑块 → 图形实时变化"的场景

## 推荐控件组合
- **主控件**：`slider` × 1~3（参数过多会让用户困惑）
- **辅助**：`toggle`（显示/隐藏辅助线）、`select`（切换函数类型）
- **反馈**：`metric`（关键数值）、`latex`（公式实时更新）

## 代码模板

```javascript
// ① 先创建所有控件
const a = EduViz.slider('振幅 A', { min: 0.1, max: 3, step: 0.1, default: 1, unit: '' })
const f = EduViz.slider('频率 f', { min: 0.1, max: 5, step: 0.1, default: 1, unit: 'Hz' })
const showGrid = EduViz.toggle('显示网格', { default: true })

// ② 展示元素
const formula = EduViz.latex('y = A\\sin(2\\pi f x)', { displayMode: true })
const ampMetric = EduViz.metric('振幅', { value: 1, unit: '', color: 'brand' })

// ③ 渲染层
const canvas = EduViz.createCanvas(520, 300)
const ax = EduViz.axis2d(canvas, { xRange: [0, 4], yRange: [-3.5, 3.5] })

// ④ 核心绘制函数
function update() {
  const A = a.value, freq = f.value
  ax.redraw(() => {
    ax.plot(x => A * Math.sin(2 * Math.PI * freq * x), { color: 'brand', width: 2 })
  })
  formula.set(`y = ${A}\\sin(2\\pi \\cdot ${freq} \\cdot x)`)
  ampMetric.set(A)
}

// ⑤ 最后统一绑 onChange（注册时立即触发 → 完成首屏绘制）
a.onChange(update)
f.onChange(update)
showGrid.onChange(v => {
  ax.redraw(() => {
    ax.plot(x => a.value * Math.sin(2 * Math.PI * f.value * x), { color: 'brand', width: 2 })
  })
})
EduViz.onThemeChange(() => update())
```

## 关键注意事项

1. **先建控件，后绑 onChange**：第一个 `onChange` 注册时立即触发，此时其他控件必须已存在
2. **update 函数读 `.value`**：不要在 onChange 回调参数里读值，直接读 `slider.value` 更清晰
3. **axis2d 的 `redraw()` 自动 clear + 画轴**：不要在 `redraw` 回调里手动 `clearRect`
4. **`metric` 颜色可动态变化**：如结果超出范围时 `m.setColor('danger')` 给用户反馈
5. **参数范围要合理**：`min` 不要设 0（会导致除零），`step` 要与 `min/max` 量级匹配

## 完整示例：导数的几何意义

```javascript
const dx = EduViz.slider('Δx', { min: 0.01, max: 3, step: 0.01, default: 2 })
const formula = EduViz.latex('\\frac{\\Delta y}{\\Delta x} = ?', { displayMode: true })
const slopeMetric = EduViz.metric('割线斜率', { value: '—', color: 'danger' })

const canvas = EduViz.createCanvas(520, 320)
const ax = EduViz.axis2d(canvas, { xRange: [-1, 5], yRange: [-1, 16] })

const f = x => x * x
const x0 = 1

function update() {
  const h = dx.value
  const slope = (f(x0 + h) - f(x0)) / h
  ax.redraw(() => {
    ax.plot(f, { color: 'brand', width: 2 })
    ax.line(
      [x0 - 0.5, f(x0) + slope * (-0.5)],
      [x0 + h + 0.5, f(x0) + slope * (h + 0.5)],
      { color: 'danger', width: 2 }
    )
    ax.point(x0, f(x0), { color: 'danger' })
    ax.point(x0 + h, f(x0 + h), { color: 'danger' })
  })
  formula.set(`\\frac{f(${(x0+h).toFixed(2)}) - f(${x0})}{${h.toFixed(2)}} = ${slope.toFixed(3)}`)
  slopeMetric.set(slope.toFixed(3))
  slopeMetric.setColor(h < 0.1 ? 'success' : 'danger')
}

dx.onChange(update)
EduViz.onThemeChange(() => update())
```
