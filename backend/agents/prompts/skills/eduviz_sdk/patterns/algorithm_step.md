---
name: algorithm_step
label: 算法步进
when_to_use: 概念的核心是"一步一步展示执行过程"——如排序、搜索、动态规划、图算法，需要学生跟着每一步理解逻辑
controls: stepper（主控件，支持自动播放）; select（切换输入数据）; button（重置/随机）; metric（比较/交换次数）; progress（完成进度）; text（当前操作说明）
---

# Pattern: algorithm_step（算法步进）

## 适用场景
- 排序算法（冒泡、快排、归并）
- 搜索算法（BFS、DFS、二分查找）
- 动态规划（填表过程）
- 图算法（Dijkstra、最小生成树）
- 任何"一步一步展示执行过程"的场景

## 推荐控件组合
- **主控件**：`stepper`（步进器，支持自动播放）
- **辅助**：`select`（切换不同输入数据）、`button`（重置/随机数据）
- **反馈**：`metric`（当前比较次数/交换次数）、`progress`（完成进度）、`text`（当前操作说明）

## 核心思路：预计算所有状态

**不要在 `onStep` 里做计算**，而是提前把所有步骤的状态存成数组，`onStep` 只负责渲染。

```javascript
// ✅ 正确：预计算所有状态
const states = []
// ... 运行算法，每一步 push 一个快照
const sp = EduViz.stepper({ total: states.length, label: '操作' })
sp.onStep(step => render(states[step]))

// ❌ 错误：在 onStep 里运行算法
sp.onStep(step => {
  runAlgorithmUntilStep(step)  // 慢、有副作用
})
```

## 代码模板

```javascript
// ① 预计算所有步骤状态
const data = [64, 34, 25, 12, 22, 11, 90]
const states = []

function precompute(arr) {
  const a = [...arr]
  states.length = 0
  states.push({ arr: [...a], highlight: [], sorted: 0, desc: '初始状态' })
  // ... 运行算法，每步 push 快照
  return states
}
precompute(data)

// ② 创建控件
const sp = EduViz.stepper({ total: states.length, label: '步骤', interval: 400 })
const cmpMetric = EduViz.metric('比较位置', { value: '—', color: 'danger' })
const prog = EduViz.progress('进度', { value: 0, max: states.length - 1, color: 'success' })
const desc = EduViz.text('初始状态')

// ③ 渲染层
const canvas = EduViz.createCanvas(500, 200)
const ctx = canvas.getContext('2d')

// ④ 渲染函数
function render(state) {
  const c = EduViz.colors()
  ctx.clearRect(0, 0, 500, 200)
  const barW = 500 / state.arr.length - 4
  state.arr.forEach((v, i) => {
    const h = v * 1.8, x = i * (barW + 4) + 2, y = 190 - h
    ctx.fillStyle = state.highlight.includes(i) ? c.danger
                  : i < state.sorted ? c.success : c.brand
    ctx.fillRect(x, y, barW, h)
    ctx.fillStyle = c.text
    ctx.font = '11px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(v, x + barW / 2, 198)
  })
}

// ⑤ 绑回调
sp.onStep(step => {
  const state = states[step]
  render(state)
  cmpMetric.set(state.highlight.length ? `[${state.highlight.join(', ')}]` : '—')
  prog.set(step)
  desc.set(state.desc)
})
EduViz.onThemeChange(() => render(states[sp.step]))
```

## 关键注意事项

1. **状态快照要深拷贝**：`states.push({ arr: [...a], ... })`，不要 push 引用
2. **`onStep` 注册时用 `step=0` 触发一次**，完成首屏绘制，不需要额外调用
3. **`interval` 建议 300~600ms**：太快看不清，太慢没耐心
4. **高亮颜色用语义色**：正在比较用 `danger`，已排序用 `success`，未处理用 `brand`
5. **`desc` 文字要说清楚"正在做什么"**：如"比较 arr[2] 和 arr[3]，需要交换"

## 完整示例：冒泡排序

```javascript
const arr = [64, 34, 25, 12, 22, 11, 90, 45]
const states = []

// 预计算
const a = [...arr]
for (let i = 0; i < a.length; i++) {
  for (let j = 0; j < a.length - i - 1; j++) {
    states.push({ arr: [...a], cmp: [j, j+1], sorted: a.length - i, desc: `比较 ${a[j]} 和 ${a[j+1]}` })
    if (a[j] > a[j+1]) {
      [a[j], a[j+1]] = [a[j+1], a[j]]
      states.push({ arr: [...a], cmp: [j, j+1], sorted: a.length - i, desc: `交换 → ${a[j]} < ${a[j+1]}` })
    }
  }
}
states.push({ arr: [...a], cmp: [], sorted: 0, desc: '排序完成 ✓' })

// 控件
const sp = EduViz.stepper({ total: states.length, label: '操作', interval: 300 })
const cmpMetric = EduViz.metric('当前比较', { value: '—', color: 'danger' })
const prog = EduViz.progress('已排序', { value: 0, max: arr.length, color: 'success' })
const descText = EduViz.text('初始状态')

// 渲染
const canvas = EduViz.createCanvas(500, 220)
const ctx = canvas.getContext('2d')

function draw(step) {
  const c = EduViz.colors()
  const st = states[step]
  ctx.clearRect(0, 0, 500, 220)
  const barW = 500 / st.arr.length - 4
  st.arr.forEach((v, i) => {
    const h = v * 1.8, x = i * (barW + 4) + 2, y = 210 - h
    ctx.fillStyle = st.cmp.includes(i) ? c.danger
                  : i >= st.sorted ? c.success : c.brand
    ctx.fillRect(x, y, barW, h)
    ctx.fillStyle = c.text
    ctx.font = '11px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(v, x + barW / 2, 218)
  })
  cmpMetric.set(st.cmp.length ? `[${st.cmp.join(', ')}]` : '完成')
  prog.set(arr.length - st.sorted)
  descText.set(st.desc)
}

sp.onStep(draw)
EduViz.onThemeChange(() => draw(sp.step))
```
