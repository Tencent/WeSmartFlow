---
name: formula_decomposition
label: 公式分步推导
when_to_use: 概念的核心是"分步骤展示推导/证明过程"——如泰勒展开、欧拉公式推导、勾股定理证明，需要学生跟着每步理解逻辑链
controls: stepper（步进推导）; slider（展开项数/精度参数）; latex（当前步骤公式）; text（步骤说明）; metric（误差/精度）; progress（推导进度）
---

# Pattern: formula_decomposition（公式分步推导）

## 适用场景
- 数学公式的逐步推导（泰勒展开、傅里叶级数）
- 物理定律的推导过程（牛顿第二定律、能量守恒）
- 证明过程的可视化（勾股定理、欧拉公式）
- 概念的层层递进（从极限到导数，从导数到积分）
- 任何"分步骤展示推导/证明"的场景

## 推荐控件组合
- **主控件**：`stepper`（步进推导）
- **辅助**：`slider`（调节展开项数、精度等参数）
- **反馈**：`latex`（当前步骤的公式）、`text`（当前步骤的文字说明）、`metric`（误差/精度）

## 核心思路：每步对应一个公式状态

```javascript
const STEPS = [
  {
    formula: 'f(x) = \\sin(x)',
    desc: '目标：用多项式近似 sin(x)',
    draw: (ax) => { ax.plot(Math.sin, { color: 'brand', width: 2 }) }
  },
  {
    formula: 'P_1(x) = x',
    desc: '一阶近似：在 x=0 处，sin(x) ≈ x',
    draw: (ax) => {
      ax.plot(Math.sin, { color: 'brand', width: 2 })
      ax.plot(x => x, { color: 'danger', width: 2 })
    }
  },
  // ...
]
```

## 代码模板

```javascript
// ① 定义推导步骤
const STEPS = [
  {
    latex: 'e^{i\\theta} = ?',
    desc: '欧拉公式：复数指数与三角函数的关系',
    highlight: null
  },
  {
    latex: 'e^x = 1 + x + \\frac{x^2}{2!} + \\frac{x^3}{3!} + \\cdots',
    desc: '回顾：e^x 的泰勒展开（在 x=0 处）',
    highlight: null
  },
  {
    latex: 'e^{i\\theta} = 1 + i\\theta + \\frac{(i\\theta)^2}{2!} + \\frac{(i\\theta)^3}{3!} + \\cdots',
    desc: '将 x 替换为 iθ',
    highlight: 'i\\theta'
  },
  {
    latex: 'e^{i\\theta} = \\left(1 - \\frac{\\theta^2}{2!} + \\frac{\\theta^4}{4!} - \\cdots\\right) + i\\left(\\theta - \\frac{\\theta^3}{3!} + \\frac{\\theta^5}{5!} - \\cdots\\right)',
    desc: '利用 i²=-1，分离实部和虚部',
    highlight: null
  },
  {
    latex: 'e^{i\\theta} = \\cos\\theta + i\\sin\\theta',
    desc: '识别出余弦和正弦的泰勒展开 → 欧拉公式！',
    highlight: null
  }
]

// ② 创建控件
const sp = EduViz.stepper({ total: STEPS.length, label: '推导步骤', interval: 2000 })
const formula = EduViz.latex(STEPS[0].latex, { displayMode: true, fontSize: 20 })
const descText = EduViz.text(STEPS[0].desc)
const progressBar = EduViz.progress('推导进度', { value: 0, max: STEPS.length - 1, color: 'brand' })

// ③ 可选：配合图形展示
const canvas = EduViz.createCanvas(400, 250)
const ax = EduViz.axis2d(canvas, { xRange: [-1.5, 1.5], yRange: [-1.5, 1.5], padding: 30 })

function drawUnitCircle(step) {
  ax.redraw(() => {
    const { ctx, toX, toY } = ax
    // 单位圆
    ctx.beginPath()
    ctx.arc(toX(0), toY(0), toX(1) - toX(0), 0, Math.PI * 2)
    ctx.strokeStyle = EduViz.colors().border
    ctx.lineWidth = 1
    ctx.stroke()

    if (step >= 4) {
      // 最后一步：展示欧拉公式的几何意义
      const theta = Math.PI / 4  // 45°
      const px = Math.cos(theta), py = Math.sin(theta)
      ax.line([0, 0], [px, py], { color: 'brand', width: 2 })
      ax.line([px, 0], [px, py], { color: 'danger', dash: [4, 4] })
      ax.line([0, 0], [px, 0], { color: 'success', dash: [4, 4] })
      ax.point(px, py, { color: 'brand', radius: 5, label: 'e^{iθ}' })
    }
  })
}

// ④ 绑回调
sp.onStep(step => {
  const s = STEPS[step]
  formula.set(s.latex)
  descText.set(s.desc)
  progressBar.set(step)
  drawUnitCircle(step)
})
EduViz.onThemeChange(() => {
  const step = sp.step
  drawUnitCircle(step)
})
```

## 关键注意事项

1. **`latex.set()` 支持动态更新公式**，每步调用一次即可
2. **步骤数不要太多**：5~10 步最佳，太多用户会失去耐心
3. **`desc` 文字要解释"为什么这一步"**，不只是描述公式
4. **`interval: 1500~2500ms`**：公式推导需要时间阅读，不要太快
5. **图形和公式要联动**：公式变化时，图形也要对应更新，增强理解
6. **最后一步要有"结论"**：明确说出推导的结果和意义

## 完整示例：泰勒展开逼近 sin(x)

```javascript
// 生成 n 阶泰勒多项式
function taylorSin(x, n) {
  let sum = 0
  for (let k = 0; k <= n; k++) {
    const sign = k % 2 === 0 ? 1 : -1
    let factorial = 1
    for (let i = 1; i <= 2*k+1; i++) factorial *= i
    sum += sign * Math.pow(x, 2*k+1) / factorial
  }
  return sum
}

const ORDERS = [1, 3, 5, 7, 9]
const STEPS = ORDERS.map((n, i) => ({
  order: n,
  latex: `P_{${n}}(x) = x${n >= 3 ? ` - \\frac{x^3}{3!}` : ''}${n >= 5 ? ` + \\frac{x^5}{5!}` : ''}${n >= 7 ? ` - \\frac{x^7}{7!}` : ''}${n >= 9 ? ` + \\cdots` : ''}`,
  desc: `${n} 阶近似：在 [-π, π] 内${n >= 7 ? '非常接近' : n >= 5 ? '较好近似' : '粗略近似'} sin(x)`
}))

const sp = EduViz.stepper({ total: STEPS.length, label: '展开阶数', interval: 1500 })
const formula = EduViz.latex(STEPS[0].latex, { displayMode: true })
const descText = EduViz.text(STEPS[0].desc)
const errorMetric = EduViz.metric('x=π 处误差', { value: '—', color: 'warning' })

const canvas = EduViz.createCanvas(520, 280)
const ax = EduViz.axis2d(canvas, { xRange: [-Math.PI * 1.2, Math.PI * 1.2], yRange: [-2, 2] })

function update(step) {
  const { order } = STEPS[step]
  ax.redraw(() => {
    ax.plot(Math.sin, { color: 'brand', width: 2.5 })
    ax.plot(x => taylorSin(x, (order - 1) / 2), { color: 'danger', width: 2, dash: [6, 3] })
  })
  formula.set(STEPS[step].latex)
  descText.set(STEPS[step].desc)
  const err = Math.abs(Math.sin(Math.PI) - taylorSin(Math.PI, (order - 1) / 2))
  errorMetric.set(err.toExponential(2))
  errorMetric.setColor(err < 0.01 ? 'success' : err < 0.1 ? 'warning' : 'danger')
}

sp.onStep(update)
EduViz.onThemeChange(() => update(sp.step))
```
