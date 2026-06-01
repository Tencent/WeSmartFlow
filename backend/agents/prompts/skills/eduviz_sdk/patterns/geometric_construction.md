---
name: geometric_construction
label: 几何构造
when_to_use: 概念的核心是"在坐标系中构造几何图形"——如向量合成、坐标变换、三角函数单位圆、矩阵变换的几何意义
controls: slider（角度/长度/坐标参数）; toggle（辅助线/标注开关）; button（重置到标准位置）; metric（角度值/长度值）; latex（几何关系公式）
---

# Pattern: geometric_construction（几何构造）

## 适用场景
- 几何作图（三角形、圆、向量）
- 向量合成与分解
- 坐标变换（旋转、缩放、平移）
- 矩阵变换的几何意义
- 三角函数的单位圆定义
- 任何"在坐标系中构造几何图形"的场景

## 推荐控件组合
- **主控件**：`slider`（角度、长度、坐标参数）
- **辅助**：`toggle`（显示/隐藏辅助线、标注）、`button`（重置到标准位置）
- **反馈**：`metric`（角度值、长度值）、`latex`（几何关系公式）

## 代码模板

```javascript
// ① 创建参数控件
const theta = EduViz.slider('角度 θ', { min: 0, max: 360, step: 1, default: 45, unit: '°' })
const showHelper = EduViz.toggle('辅助线', { default: true })

// ② 展示元素
const sinMetric = EduViz.metric('sin θ', { value: '0.00', color: 'danger' })
const cosMetric = EduViz.metric('cos θ', { value: '0.00', color: 'success' })
const formula = EduViz.latex('\\sin^2\\theta + \\cos^2\\theta = 1', { displayMode: true })

// ③ 渲染层（几何场景推荐 axis2d，坐标系已内置）
const canvas = EduViz.createCanvas(400, 400)
const ax = EduViz.axis2d(canvas, {
  xRange: [-1.5, 1.5],
  yRange: [-1.5, 1.5],
  padding: 40
})

// ④ 渲染函数
function update() {
  const rad = theta.value * Math.PI / 180
  const px = Math.cos(rad), py = Math.sin(rad)

  ax.redraw(() => {
    // 画单位圆（用 plot 参数化）
    // 注意：axis2d.plot 是 y=f(x) 形式，画圆需要用 ctx 直接画
    const { ctx, toX, toY } = ax
    ctx.beginPath()
    ctx.arc(toX(0), toY(0), toX(1) - toX(0), 0, Math.PI * 2)
    ctx.strokeStyle = EduViz.colors().border
    ctx.lineWidth = 1.5
    ctx.stroke()

    // 画半径
    ax.line([0, 0], [px, py], { color: 'brand', width: 2 })
    ax.point(px, py, { color: 'brand', radius: 6 })

    if (showHelper.value) {
      // 画投影辅助线
      ax.line([px, 0], [px, py], { color: 'danger', dash: [4, 4], width: 1 })
      ax.line([0, py], [px, py], { color: 'success', dash: [4, 4], width: 1 })
      // 标注
      ax.point(px, 0, { color: 'danger', radius: 4, label: `cos=${px.toFixed(2)}` })
      ax.point(0, py, { color: 'success', radius: 4, label: `sin=${py.toFixed(2)}` })
    }
  })

  sinMetric.set(py.toFixed(4))
  cosMetric.set(px.toFixed(4))
  sinMetric.setColor(py >= 0 ? 'danger' : 'warning')
}

// ⑤ 绑回调
theta.onChange(update)
showHelper.onChange(update)
EduViz.onThemeChange(() => update())
```

## 关键注意事项

1. **`axis2d.plot` 只支持 `y=f(x)` 形式**，画圆/椭圆等参数曲线需要用 `ax.ctx` 直接画
2. **`ax.toX(x)` / `ax.toY(y)` 转换坐标**：数学坐标 → canvas 像素，自定义绘制时必用
3. **`ax.redraw()` 会自动 clear + 画轴**，不要在回调里手动 clearRect
4. **角度 slider 建议 0~360°**，内部转换为弧度：`const rad = deg * Math.PI / 180`
5. **辅助线用 `dash` 参数**：`{ dash: [4, 4] }` 画虚线，视觉上与主要图形区分
6. **`padding: 40` 给坐标轴标签留空间**，避免数字被裁切

## 完整示例：向量加法

```javascript
const ax1 = EduViz.slider('向量 a 角度', { min: 0, max: 360, step: 1, default: 30, unit: '°' })
const al = EduViz.slider('向量 a 长度', { min: 0.5, max: 2, step: 0.1, default: 1.5 })
const bx1 = EduViz.slider('向量 b 角度', { min: 0, max: 360, step: 1, default: 120, unit: '°' })
const bl = EduViz.slider('向量 b 长度', { min: 0.5, max: 2, step: 0.1, default: 1.2 })

const resultMetric = EduViz.metric('|a+b|', { value: '—', color: 'brand' })
const formula = EduViz.latex('\\vec{c} = \\vec{a} + \\vec{b}', { displayMode: true })

const canvas = EduViz.createCanvas(420, 380)
const ax = EduViz.axis2d(canvas, { xRange: [-3, 3], yRange: [-3, 3], padding: 40 })

function drawArrow(ctx, x1, y1, x2, y2, color) {
  const c = EduViz.colors()
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.stroke()
  // 箭头头部
  const angle = Math.atan2(y2 - y1, x2 - x1)
  const size = 10
  ctx.beginPath()
  ctx.moveTo(x2, y2)
  ctx.lineTo(x2 - size * Math.cos(angle - 0.4), y2 - size * Math.sin(angle - 0.4))
  ctx.lineTo(x2 - size * Math.cos(angle + 0.4), y2 - size * Math.sin(angle + 0.4))
  ctx.closePath()
  ctx.fill()
}

function update() {
  const c = EduViz.colors()
  const aRad = ax1.value * Math.PI / 180
  const bRad = bx1.value * Math.PI / 180
  const aVec = { x: al.value * Math.cos(aRad), y: al.value * Math.sin(aRad) }
  const bVec = { x: bl.value * Math.cos(bRad), y: bl.value * Math.sin(bRad) }
  const cVec = { x: aVec.x + bVec.x, y: aVec.y + bVec.y }

  ax.redraw(() => {
    const { ctx, toX, toY } = ax
    // 向量 a（从原点出发）
    drawArrow(ctx, toX(0), toY(0), toX(aVec.x), toY(aVec.y), c.brand)
    // 向量 b（从 a 的终点出发）
    drawArrow(ctx, toX(aVec.x), toY(aVec.y), toX(cVec.x), toY(cVec.y), c.success)
    // 合向量 c（从原点到终点）
    drawArrow(ctx, toX(0), toY(0), toX(cVec.x), toY(cVec.y), c.danger)
    // 标注
    ax.point(aVec.x, aVec.y, { color: 'brand', radius: 4, label: 'a' })
    ax.point(cVec.x, cVec.y, { color: 'danger', radius: 4, label: 'a+b' })
  })

  const len = Math.sqrt(cVec.x ** 2 + cVec.y ** 2)
  resultMetric.set(len.toFixed(3))
}

ax1.onChange(update)
al.onChange(update)
bx1.onChange(update)
bl.onChange(update)
EduViz.onThemeChange(() => update())
```
