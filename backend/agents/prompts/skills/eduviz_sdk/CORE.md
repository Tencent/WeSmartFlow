---
name: eduviz_sdk_core
description: EduViz SDK 完整 API 参考（Coder 必读）
---

# EduViz SDK 完整 API 参考

运行环境：iframe 沙箱，全局 `EduViz` 已注入，外层是 `async function`，可直接 `await`。

> **黄金法则：只调用本文档中明确列出的方法和属性。文档中没有的方法一律不存在，不要猜测或发明。**

---

## 编写规范（违反直接报错）

1. **直接写顶层代码**，不要包 `function` / IIFE / `<script>` / `<html>`
2. **可以 `await`**，第三方库必须 `await EduViz.loadLib('p5')` 后才能用
3. **不要 `import` / `require`**，库加载后通过全局变量使用
4. **动画用 `EduViz.timeline().onFrame`**，不要 `setInterval` / `while(true)`
5. **颜色必须从 `EduViz.colors()` 取**，禁止硬编码 `#fff` / `#ef4444` 等
6. **每个控件都必须绑 `onChange` / `onStep` / `onFrame`**，否则拖了没反应
7. **先创建所有控件，最后统一绑回调**，避免回调触发时其他控件未创建
8. **代码控制在 120 行内**

---

## 控件 API — 完整列表

### `EduViz.slider(name, opts)` → SliderCtrl

拖动调参控件，创建后自动挂载到控件区。

**参数：**
```javascript
EduViz.slider('名称', {
  min: 0,          // 最小值（默认 0）
  max: 1,          // 最大值（默认 1）
  step: 0.01,      // 步长（默认自动推断）
  default: 0,      // 初始值（默认 min）
  label: '显示名', // 标签文字（默认用 name）
  unit: 'px',      // 单位后缀（可选）
  showValue: true, // 是否显示当前值（默认 true）
})
```

**SliderCtrl 完整 API：**
```javascript
s.value              // 【属性】读取当前值（只读）
s.min                // 【属性】读/写最小值
s.max                // 【属性】读/写最大值
s.step               // 【属性】读/写步长
s.onChange(fn)       // 【方法】注册回调 fn(value)，注册时立即触发一次；返回 ctrl（可链式）
s.setValue(v)        // 【方法】程序化设置值并触发回调；返回 ctrl
```

❌ **不存在的方法**：`s.update()` `s.set()` `s.on()` `s.subscribe()`

---

### `EduViz.timeline(opts)` → TimelineCtrl

连续动画控件（播放/暂停 + 进度条）。

**参数：**
```javascript
EduViz.timeline({
  duration: 5,      // 总时长（秒，默认 5）
  fps: 30,          // 帧率（默认 30）
  loop: false,      // 是否循环（默认 false）
  autoPlay: false,  // 是否自动播放（默认 false）
})
```

**TimelineCtrl 完整 API：**
```javascript
tl.time              // 【属性】当前时间（秒，只读）
tl.playing           // 【属性】是否正在播放（只读）
tl.duration          // 【属性】读/写总时长（秒）
tl.onFrame(fn)       // 【方法】注册帧回调 fn(time, dt)，注册时用 (0,0) 触发一次；返回 ctrl
tl.play()            // 【方法】开始播放；返回 ctrl
tl.pause()           // 【方法】暂停；返回 ctrl
tl.reset()           // 【方法】暂停并归零，触发一次 onFrame(0,0)；返回 ctrl
tl.seek(t)           // 【方法】跳转到指定时间（秒），触发一次 onFrame；返回 ctrl
```

❌ **不存在的方法**：`tl.update()` `tl.set()` `tl.stop()` `tl.on()` `tl.tick()`

---

### `EduViz.stepper(opts)` → StepperCtrl

算法步进控件（上一步/下一步/自动播放）。

**参数：**
```javascript
EduViz.stepper({
  total: 10,        // 总步数（默认 10）
  label: '步骤',    // 标签文字（默认 '步骤'）
  interval: 800,    // 自动播放间隔（毫秒，默认 800）
  autoPlay: false,  // 是否自动播放（默认 false）
})
```

**StepperCtrl 完整 API：**
```javascript
sp.step              // 【属性】当前步骤索引（0-based，只读）
sp.total             // 【属性】读/写总步数（写入时自动 clamp 当前步骤）
sp.interval          // 【属性】读/写自动播放间隔（毫秒）
sp.onStep(fn)        // 【方法】注册步骤回调 fn(step)，注册时立即触发一次；返回 ctrl
sp.next()            // 【方法】前进一步（到末尾时自动暂停）；返回 ctrl
sp.prev()            // 【方法】后退一步；返回 ctrl
sp.goto(s)           // 【方法】跳转到指定步骤并触发回调；返回 ctrl
sp.reset()           // 【方法】暂停并回到步骤 0，触发一次 onStep(0)；返回 ctrl
sp.play()            // 【方法】开始自动步进；返回 ctrl
sp.pause()           // 【方法】暂停自动步进；返回 ctrl
```

❌ **不存在的方法**：`sp.update()` `sp.set()` `sp.setStep()` `sp.on()` `sp.setValue()` `sp.setTotal()`
> `total` 是可写属性，直接赋值：`sp.total = 20`，不要调用 `sp.setTotal(20)`

---

### `EduViz.toggle(name, opts)` → ToggleCtrl

开关控件。

**参数：**
```javascript
EduViz.toggle('名称', {
  default: false,  // 初始状态（默认 false）
  label: '显示名', // 标签文字（默认用 name）
})
```

**ToggleCtrl 完整 API：**
```javascript
t.value              // 【属性】当前布尔值（只读）
t.onChange(fn)       // 【方法】注册回调 fn(value)，注册时立即触发一次；返回 ctrl
t.setValue(v)        // 【方法】程序化设置值并触发回调；返回 ctrl
```

❌ **不存在的方法**：`t.update()` `t.set()` `t.toggle()` `t.on()`

---

### `EduViz.select(name, opts)` → SelectCtrl

下拉选择控件。

**参数：**
```javascript
EduViz.select('名称', {
  choices: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
  default: 'a',    // 初始选中值（默认第一项）
  label: '显示名', // 标签文字（默认用 name）
})
```

**SelectCtrl 完整 API：**
```javascript
sel.value              // 【属性】当前选中值（只读）
sel.onChange(fn)       // 【方法】注册回调 fn(value)，注册时立即触发一次；返回 ctrl
sel.setValue(v)        // 【方法】程序化设置选中值并触发回调；返回 ctrl
sel.setChoices(arr)    // 【方法】动态替换选项列表 arr=[{value,label},...]；返回 ctrl
```

❌ **不存在的方法**：`sel.update()` `sel.set()` `sel.on()` `sel.setOptions()`

---

### `EduViz.button(label, opts)` → ButtonCtrl

按钮控件。

**参数：**
```javascript
EduViz.button('重置', {
  variant: 'primary', // 'primary'|'default'|'success'|'warning'|'danger'（默认 'default'）
})
```

**ButtonCtrl 完整 API：**
```javascript
btn.onClick(fn)        // 【方法】注册点击回调 fn()；返回 ctrl（可链式）
btn.setLabel(text)     // 【方法】更新按钮文字；返回 ctrl
btn.setDisabled(bool)  // 【方法】设置禁用状态；返回 ctrl
btn.setVariant(v)      // 【方法】切换样式变体；返回 ctrl
btn.el                 // 【属性】原生 DOM button 元素
```

❌ **不存在的方法**：`btn.update()` `btn.on()` `btn.setText()` `btn.disable()`

---

## 渲染 API — 完整列表

### `EduViz.createCanvas(width, height)` → HTMLCanvasElement

创建并挂载 canvas 到可视化区，已处理 Retina DPR，`ctx.scale(dpr,dpr)` 已调用。

```javascript
const canvas = EduViz.createCanvas(520, 320)
const ctx = canvas.getContext('2d')
// 直接用 CSS 像素坐标绘图，无需手动处理 DPR
```

---

### `EduViz.axis2d(canvas, opts)` → Axis2DApi

2D 坐标系辅助（函数/几何场景首选），自动处理坐标转换、网格、坐标轴。

**参数：**
```javascript
EduViz.axis2d(canvas, {
  xRange: [-5, 5],   // x 轴范围（默认 [-5,5]）
  yRange: [-5, 5],   // y 轴范围（默认 [-5,5]）
  showGrid: true,    // 是否显示网格（默认 true）
  showAxis: true,    // 是否显示坐标轴和刻度（默认 true）
  padding: 40,       // 内边距像素（默认 40）
})
```

**Axis2DApi 完整 API：**
```javascript
ax.ctx               // 【属性】原生 CanvasRenderingContext2D
ax.canvas            // 【属性】原生 HTMLCanvasElement
ax.toX(x)            // 【方法】数学坐标 → canvas 像素 X
ax.toY(y)            // 【方法】数学坐标 → canvas 像素 Y
ax.clear()           // 【方法】清空画布
ax.drawAxes()        // 【方法】绘制网格和坐标轴
ax.redraw(fn)        // 【方法】clear → drawAxes → fn(api)，一键重绘
ax.plot(fn, opts)    // 【方法】绘制函数曲线 y=fn(x)
                     //   opts: { color:'brand', width:2, samples:200, dash:[4,4] }
ax.point(x, y, opts) // 【方法】标记一个点
                     //   opts: { color:'danger', radius:5, label:'A' }
ax.line(p1, p2, opts)// 【方法】绘制线段，p1/p2 为 [x,y]
                     //   opts: { color:'success', width:2, dash:[4,4] }
ax.setRange(xR, yR)  // 【方法】更新坐标范围；返回 api
```

❌ **不存在的方法**：`ax.update()` `ax.render()` `ax.draw()` `ax.reset()`

---

### `EduViz.getContainer()` → HTMLDivElement

返回可视化区容器 div，用于挂载第三方库（D3 SVG、Three.js canvas 等）。

```javascript
const container = EduViz.getContainer()
// 示例：D3 挂载
const svg = d3.select(container).append('svg')
```

---

## 展示 API — 完整列表

### `EduViz.metric(label, opts)` → MetricCtrl

大号数字徽标，用于实时反馈关键指标。

```javascript
EduViz.metric('斜率', {
  value: 0,        // 初始值（默认 '—'）
  unit: '',        // 单位（默认空）
  color: 'brand',  // 颜色：'brand'|'success'|'warning'|'danger'|'info'|'text'
})
```

**MetricCtrl 完整 API：**
```javascript
m.set(value, unit)   // 【方法】更新数值（unit 可选，传 undefined 则不更新单位）；返回 this
m.setColor(color)    // 【方法】更新颜色；返回 this
```

❌ **不存在的方法**：`m.update()` `m.setValue()` `m.setText()`

---

### `EduViz.progress(label, opts)` → ProgressCtrl

进度条，显示 0-100% 的比例量。

```javascript
EduViz.progress('已排序', {
  value: 0,          // 初始值（默认 0）
  max: 1,            // 最大值（默认 1）
  color: 'brand',    // 颜色
  showText: true,    // 是否显示百分比文字
})
```

**ProgressCtrl 完整 API：**
```javascript
p.set(value)         // 【方法】更新当前值（自动换算百分比，value/max*100%）；返回 this
p.setColor(color)    // 【方法】更新颜色；返回 this
```

❌ **不存在的方法**：`p.update()` `p.setValue()` `p.setProgress()`

---

### `EduViz.latex(expr, opts)` → LatexCtrl

渲染 LaTeX 公式（依赖内置 KaTeX，无需 loadLib）。

```javascript
EduViz.latex('f(x) = x^2', {
  displayMode: true, // 是否块级显示（默认 true）
  fontSize: 16,      // 字号（默认 16）
})
```

**LatexCtrl 完整 API：**
```javascript
f.set(expr)          // 【方法】更新公式字符串并重新渲染（无返回值）
```

❌ **不存在的方法**：`f.update()` `f.render()` `f.setValue()`

---

### `EduViz.text(content)` → TextCtrl

纯文本展示。

**TextCtrl 完整 API：**
```javascript
info.set(text)       // 【方法】更新文字内容（无返回值）
```

❌ **不存在的方法**：`info.update()` `info.setText()` `info.setValue()`

---

## 响应式状态

### `EduViz.state(initial)` → StateProxy

创建响应式状态对象，属性变化时自动触发 watcher。

```javascript
const s = EduViz.state({ x: 0, mode: 'linear' })
s.x = 1.5            // 直接赋值触发所有该 key 的 watcher
s.$watch('x', (newVal, oldVal) => { /* 响应变化 */ })
// $watch 注册时立即用当前值触发一次（oldVal 为 undefined）
// 注意：$watch 是 StateProxy 上的特殊方法，不是普通属性
```

❌ **不存在的方法**：`s.watch()` `s.on()` `s.subscribe()` `s.get()` `s.set()`

---

## 颜色与主题

```javascript
const c = EduViz.colors()
// 可用字段：c.bg, c.panel, c.border, c.text, c.textSec, c.textMuted,
//           c.brand, c.track, c.success, c.warning, c.danger, c.info

// 正确用法：立即着色 + 注册主题回调（二者缺一不可）
function applyColors(c) { /* 更新所有颜色相关代码 */ }
applyColors(EduViz.colors())                  // ← 必须先调一次！
EduViz.onThemeChange((theme, c) => applyColors(c))
// onThemeChange 返回一个取消订阅函数：const unsubscribe = EduViz.onThemeChange(...)

// 主动切换主题（通常由父页面控制，但代码内也可调用）
EduViz.setTheme('dark')   // 'dark' | 'light'
EduViz.setTheme('light')

// metric/progress/button 的 color 参数接受语义色名：
// 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'text'
// 也接受 CSS 色值：'#ff0000' | 'rgb(255,0,0)'
```

**p5.js 不需要 `onThemeChange`**（`draw()` 每帧重读 `colors()` 自动跟随）

---

## 可用第三方库

| 调用 | 全局变量 | 用途 |
|------|---------|------|
| `await EduViz.loadLib('p5')` | `p5` | 创意绘图、Canvas 动画 |
| `await EduViz.loadLib('d3')` | `d3` | SVG 数据可视化 |
| `await EduViz.loadLib('three')` | `THREE` | 3D WebGL |
| `await EduViz.loadLib('matter')` | `Matter` | 2D 物理引擎 |
| `await EduViz.loadLib('plotly')` | `Plotly` | 函数曲线、热力图 |
| `await EduViz.loadLib('chart')` | `Chart` | 统计图表 |
| `await EduViz.loadLib('mathjs')` | `math` | 矩阵、符号计算 |
| `await EduViz.loadLib('anime')` | `anime` | CSS/JS 动画 |
| `await EduViz.loadLib('cytoscape')` | `cytoscape` | 图/网络可视化 |
| `await EduViz.loadLib('tone')` | `Tone` | 音频合成 |
| KaTeX | 内置，直接用 `EduViz.latex()` | 数学公式 |

---

## 常见错误模式（必须避免）

```javascript
// ❌ 错误：调用不存在的方法
sp.update(3)          // stepper 没有 update()，应用 sp.goto(3)
sp.setTotal(20)       // 没有 setTotal()，应用 sp.total = 20
m.update(2.5)         // metric 没有 update()，应用 m.set(2.5)
ax.render()           // axis2d 没有 render()，应用 ax.redraw(fn)
f.render('x^2')       // latex 没有 render()，应用 f.set('x^2')
tl.stop()             // timeline 没有 stop()，应用 tl.pause() 或 tl.reset()

// ❌ 错误：忘记绑回调
const sp = EduViz.stepper({ total: 5 })
// 直接用 sp.step 而不绑 onStep → 步进时画面不更新

// ✅ 正确：每个控件都必须绑回调
sp.onStep(step => draw(step))

// ❌ 错误：在回调外读控件值
const s = EduViz.slider('x', { min: 0, max: 10 })
draw(s.value)  // 只执行一次，之后拖动不更新

// ✅ 正确：在 onChange 回调里响应变化
s.onChange(v => draw(v))
```
