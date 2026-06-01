---
name: time_evolution
label: 时间演化
when_to_use: 概念的核心是"随时间连续变化的动态过程"——如物理仿真、微分方程、生态动力学，需要播放/暂停来观察演化
controls: timeline（主控件，带播放/暂停/进度条）; slider（初始参数）; button（重置）; metric（当前时刻关键量）; latex（运动方程）
---

# Pattern: time_evolution（时间演化）

## 适用场景
- 物理仿真（抛体运动、弹簧振子、单摆）
- 传播过程（热传导、波的传播、扩散）
- 微分方程数值解（欧拉法、RK4）
- 生态系统动力学（捕食者-猎物模型）
- 任何"随时间连续变化"的动态过程

## 推荐控件组合
- **主控件**：`timeline`（时间轴，带播放/暂停/进度条）
- **辅助**：`slider`（调节初始参数，如初速度、质量）、`button`（重置）
- **反馈**：`metric`（当前时刻的关键量）、`latex`（运动方程）

## 核心思路：onFrame 里做物理计算

```javascript
const tl = EduViz.timeline({ duration: 10, fps: 60, loop: true, autoPlay: false })
tl.onFrame((time, dt) => {
  // time: 当前秒数（0 ~ duration）
  // dt: 帧间隔秒（约 1/fps）
  // 在这里更新物理状态并重绘
  updatePhysics(time)
  render()
})
```

## 代码模板

```javascript
// ① 创建参数控件（改参数需要重置动画）
const v0 = EduViz.slider('初速度', { min: 1, max: 20, step: 0.5, default: 10, unit: 'm/s' })
const angle = EduViz.slider('角度', { min: 10, max: 80, step: 1, default: 45, unit: '°' })
const resetBtn = EduViz.button('重置', { variant: 'primary' })

// ② 展示元素
const timeMetric = EduViz.metric('时间', { value: '0.00', unit: 's', color: 'info' })
const heightMetric = EduViz.metric('高度', { value: '0.00', unit: 'm', color: 'brand' })

// ③ 渲染层
const canvas = EduViz.createCanvas(520, 300)
const ax = EduViz.axis2d(canvas, { xRange: [0, 25], yRange: [0, 15] })

// ④ 物理计算函数
function getPos(t) {
  const rad = angle.value * Math.PI / 180
  const vx = v0.value * Math.cos(rad)
  const vy = v0.value * Math.sin(rad)
  const x = vx * t
  const y = vy * t - 0.5 * 9.8 * t * t
  return { x, y: Math.max(0, y) }
}

// ⑤ 渲染函数
function render(time) {
  const pos = getPos(time)
  ax.redraw(() => {
    // 画轨迹
    ax.plot(t => {
      const p = getPos(t)
      return p.y > 0 ? p.y : null
    }, { color: 'brand', width: 1, samples: 100 })
    // 画当前位置
    ax.point(pos.x, pos.y, { color: 'danger', radius: 8 })
  })
  timeMetric.set(time.toFixed(2))
  heightMetric.set(pos.y.toFixed(2))
}

// ⑥ 时间轴
const tl = EduViz.timeline({ duration: 5, fps: 60, loop: false, autoPlay: false })
tl.onFrame((time) => render(time))

// ⑦ 参数改变时重置
function resetAnim() { tl.reset(); render(0) }
v0.onChange(resetAnim)
angle.onChange(resetAnim)
resetBtn.onClick(() => resetAnim())
EduViz.onThemeChange(() => render(tl.time))
```

## 关键注意事项

1. **`onFrame` 注册时用 `(0, 0)` 触发一次**，完成首屏绘制
2. **参数 slider 改变时要重置 timeline**：`tl.reset()` 后再 `render(0)`，否则画面不更新
3. **`loop: true` 适合周期运动**（单摆、弹簧），`loop: false` 适合单次过程（抛体）
4. **物理计算用解析解而非数值积分**（如果有解析解）：更稳定，不会累积误差
5. **`fps: 60` 是上限**，实际帧率由浏览器决定，不要依赖精确帧率做计算
6. **暂停后改参数也要重绘**：`onChange` 里显式调 `render(tl.time)`

## 完整示例：弹簧振子

```javascript
const mass = EduViz.slider('质量 m', { min: 0.1, max: 5, step: 0.1, default: 1, unit: 'kg' })
const k = EduViz.slider('弹簧系数 k', { min: 1, max: 20, step: 0.5, default: 5, unit: 'N/m' })
const x0 = EduViz.slider('初始位移 x₀', { min: -3, max: 3, step: 0.1, default: 2, unit: 'm' })

const periodMetric = EduViz.metric('周期 T', { value: '—', unit: 's', color: 'brand' })
const posMetric = EduViz.metric('位移 x', { value: '0.00', unit: 'm', color: 'info' })

const canvas = EduViz.createCanvas(520, 280)
const ax = EduViz.axis2d(canvas, { xRange: [0, 12], yRange: [-3.5, 3.5] })

function getX(t) {
  const omega = Math.sqrt(k.value / mass.value)
  return x0.value * Math.cos(omega * t)
}

function render(time) {
  const T = 2 * Math.PI / Math.sqrt(k.value / mass.value)
  ax.redraw(() => {
    ax.plot(t => getX(t), { color: 'brand', width: 2, samples: 300 })
    ax.point(time, getX(time), { color: 'danger', radius: 7, label: 'x(t)' })
    ax.line([time, -3.5], [time, 3.5], { color: 'danger', dash: [4, 4], width: 1 })
  })
  periodMetric.set(T.toFixed(2))
  posMetric.set(getX(time).toFixed(3))
}

const tl = EduViz.timeline({ duration: 12, fps: 60, loop: true, autoPlay: false })
tl.onFrame(time => render(time))

function reset() { tl.reset(); render(0) }
mass.onChange(reset)
k.onChange(reset)
x0.onChange(reset)
EduViz.onThemeChange(() => render(tl.time))
```
