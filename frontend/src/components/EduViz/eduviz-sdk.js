/**
 * EduViz SDK v2 — 轻量核心
 *
 * 设计理念：SDK 只负责「控件 + 状态 + 布局 + 通信 + 库加载」
 * 渲染层完全交给第三方库（p5.js / D3 / Three.js / Matter.js 等）
 * Agent 直接生成第三方库的原生代码，LLM 对这些库的 API 已经非常熟悉
 */
(function () {
  "use strict";

  // ═══════════════════════════════════════════════════════════
  // 第三方库 CDN 注册表
  // ═══════════════════════════════════════════════════════════
  const LIB_REGISTRY = {
    p5: {
      url: "https://cdn.jsdelivr.net/npm/p5@1.9.4/lib/p5.min.js",
      global: "p5",
    },
    d3: {
      url: "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js",
      global: "d3",
    },
    three: {
      url: "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js",
      global: "THREE",
    },
    matter: {
      url: "https://cdn.jsdelivr.net/npm/matter-js@0.19.0/build/matter.min.js",
      global: "Matter",
    },
    tone: {
      url: "https://cdn.jsdelivr.net/npm/tone@14.7.77/build/Tone.min.js",
      global: "Tone",
    },
    mathjs: {
      url: "https://cdn.jsdelivr.net/npm/mathjs@12.4.0/lib/browser/math.min.js",
      global: "math",
    },
    anime: {
      url: "https://cdn.jsdelivr.net/npm/animejs@3.2.2/lib/anime.min.js",
      global: "anime",
    },
    chart: {
      url: "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
      global: "Chart",
    },
    plotly: {
      url: "https://cdn.jsdelivr.net/npm/plotly.js-dist@2.35.2/plotly.min.js",
      global: "Plotly",
    },
    katex: {
      url: "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js",
      global: "katex",
      css: "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css",
    },
    cytoscape: {
      url: "https://cdn.jsdelivr.net/npm/cytoscape@3.28.1/dist/cytoscape.min.js",
      global: "cytoscape",
    },
  };

  const _loadedLibs = {};
  const _loadingPromises = {};

  /**
   * 按需加载第三方库
   * @param {...string} libNames - 库名称（如 'p5', 'd3', 'three'）
   * @returns {Promise} 所有库加载完成后 resolve
   */
  async function loadLib(...libNames) {
    const promises = libNames.map((name) => {
      if (_loadedLibs[name])
        return Promise.resolve(window[LIB_REGISTRY[name].global]);
      if (_loadingPromises[name]) return _loadingPromises[name];

      const lib = LIB_REGISTRY[name];
      if (!lib) {
        // 未知库名立即报错，LLM 第一时间能看到，避免后续代码梦魇反复
        return Promise.reject(
          new Error(
            `[EduViz] 未知库名: "${name}"，允许值：${Object.keys(LIB_REGISTRY).join(", ")}`,
          ),
        );
      }

      const p = new Promise((resolve, reject) => {
        // 加载 CSS（如果有）
        if (lib.css) {
          const link = document.createElement("link");
          link.rel = "stylesheet";
          link.href = lib.css;
          document.head.appendChild(link);
        }
        // 加载 JS
        const script = document.createElement("script");
        script.src = lib.url;
        script.onload = () => {
          _loadedLibs[name] = true;
          delete _loadingPromises[name]; // 清理缓存，允许 reload 后重新加载
          resolve(window[lib.global]);
        };
        script.onerror = () => {
          // 失败后清理缓存，允许下次重试
          delete _loadingPromises[name];
          reject(new Error(`[EduViz] 加载 ${name} 失败: ${lib.url}`));
        };
        document.head.appendChild(script);
      });
      _loadingPromises[name] = p;
      return p;
    });

    await Promise.all(promises);
  }

  // ═══════════════════════════════════════════════════════════
  // 内部状态 & 主题（基于 CSS 变量驱动，控件&用户代码统一从 colors() 取色）
  // ═══════════════════════════════════════════════════════════
  const _state = {
    theme: "dark",
    container: null,
    controlsEl: null,
    vizEl: null,
    infoEl: null,
  };

  // 注入主题样式（一次）
  function injectThemeStyle() {
    if (document.getElementById("eduviz-theme-style")) return;
    const style = document.createElement("style");
    style.id = "eduviz-theme-style";
    style.textContent = `
      :root {
        --ev-bg: #0e0f14;
        --ev-panel: #13141a;
        --ev-border: rgba(255,255,255,0.08);
        --ev-text: #eeeef0;
        --ev-text-sec: #9394a5;
        --ev-text-muted: #5f6070;
        --ev-brand: #6366f1;
        --ev-track: rgba(255,255,255,0.18);
        --ev-success: #10b981;
        --ev-warning: #f59e0b;
        --ev-danger:  #ef4444;
        --ev-info:    #3b82f6;
      }
      [data-theme="light"] {
        --ev-bg: #ffffff;
        --ev-panel: #f7f8fa;
        --ev-border: rgba(0,0,0,0.10);
        --ev-text: #111118;
        --ev-text-sec: #52525b;
        --ev-text-muted: #71717a;
        --ev-brand: #5b5bd6;
        --ev-track: rgba(0,0,0,0.18);
        --ev-success: #059669;
        --ev-warning: #d97706;
        --ev-danger:  #dc2626;
        --ev-info:    #2563eb;
      }
      html, body { background: var(--ev-bg); color: var(--ev-text); transition: background 0.18s ease, color 0.18s ease; }
      .ev-slider-track { -webkit-appearance: none; appearance: none; width: 100%; height: 4px; border-radius: 2px; background: var(--ev-track); cursor: pointer; outline: none; }
      .ev-slider-track::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px; border-radius: 50%; background: var(--ev-brand); cursor: pointer; box-shadow: 0 1px 4px rgba(0,0,0,0.25); }
      .ev-slider-track::-moz-range-thumb { width: 14px; height: 14px; border-radius: 50%; background: var(--ev-brand); cursor: pointer; border: none; }
    `;
    document.head.appendChild(style);
  }

  // 实时从 CSS 变量读取真实色值（用于 canvas 等需要具体色的场景）
  function readVar(name, fallback) {
    try {
      const v = getComputedStyle(document.documentElement)
        .getPropertyValue(name)
        .trim();
      return v || fallback;
    } catch {
      return fallback;
    }
  }

  function colors() {
    return {
      bg: readVar("--ev-bg", "#0e0f14"),
      panel: readVar("--ev-panel", "#13141a"),
      border: readVar("--ev-border", "rgba(255,255,255,0.08)"),
      text: readVar("--ev-text", "#eeeef0"),
      textSec: readVar("--ev-text-sec", "#9394a5"),
      textMuted: readVar("--ev-text-muted", "#5f6070"),
      brand: readVar("--ev-brand", "#6366f1"),
      track: readVar("--ev-track", "rgba(255,255,255,0.18)"),
      // 语义色（用于状态/对比，自动跟随 dark/light）
      success: readVar("--ev-success", "#10b981"),
      warning: readVar("--ev-warning", "#f59e0b"),
      danger: readVar("--ev-danger", "#ef4444"),
      info: readVar("--ev-info", "#3b82f6"),
    };
  }

  function applyThemeToBody() {
    document.documentElement.setAttribute("data-theme", _state.theme);
  }

  // ═══════════════════════════════════════════════════════════
  // DOM 辅助
  // ═══════════════════════════════════════════════════════════
  function el(tag, style = {}, children = []) {
    const e = document.createElement(tag);
    Object.assign(e.style, style);
    children.forEach((c) => {
      if (typeof c === "string") e.appendChild(document.createTextNode(c));
      else if (c) e.appendChild(c);
    });
    return e;
  }

  // 用 rAF 节流，避免动画期间高频 postMessage
  let _resizePending = false;
  function notifyResize() {
    if (_resizePending) return;
    _resizePending = true;
    requestAnimationFrame(() => {
      _resizePending = false;
      const h = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
      );
      window.parent.postMessage({ type: "resize", height: h }, "*");
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 布局初始化
  // ═══════════════════════════════════════════════════════════
  function initLayout() {
    injectThemeStyle();
    document.documentElement.setAttribute("data-theme", _state.theme);
    document.body.style.cssText = `margin:0;padding:16px;font-family:Inter,-apple-system,sans-serif;font-size:13px;line-height:1.5;overflow:visible;`;
    _state.container = el("div", {
      display: "flex",
      flexDirection: "column",
      gap: "12px",
    });
    _state.controlsEl = el("div", {
      display: "flex",
      flexWrap: "wrap",
      gap: "12px",
      alignItems: "flex-end",
    });
    _state.vizEl = el("div", {
      display: "flex",
      flexDirection: "column",
      gap: "12px",
      width: "100%",
      overflow: "visible",
    });
    _state.infoEl = el("div", {
      display: "flex",
      flexDirection: "column",
      gap: "8px",
    });
    _state.container.append(_state.controlsEl, _state.vizEl, _state.infoEl);
    document.body.appendChild(_state.container);
    new ResizeObserver(notifyResize).observe(document.body);
    // 监听 vizEl 子树变化（canvas/svg append 后立即上报高度）
    new MutationObserver(notifyResize).observe(_state.vizEl, {
      childList: true,
      subtree: true,
    });
  }

  // ═══════════════════════════════════════════════════════════
  // 响应式状态管理
  // ═══════════════════════════════════════════════════════════
  function state(initial = {}) {
    const watchers = {};
    const proxy = new Proxy(
      { ...initial },
      {
        set(target, key, value) {
          const old = target[key];
          target[key] = value;
          if (old !== value && watchers[key]) {
            watchers[key].forEach((fn) => {
              try {
                fn(value, old);
              } catch (e) {
                console.error("[EduViz] state watcher error:", e);
              }
            });
          }
          return true;
        },
      },
    );
    // $watch：注册时立即用当前值触发一次，与控件 onChange 行为对齐
    proxy.$watch = (key, fn) => {
      if (!watchers[key]) watchers[key] = [];
      watchers[key].push(fn);
      try {
        fn(proxy[key], undefined);
      } catch (e) {
        console.error("[EduViz] state $watch init error:", e);
      }
    };
    return proxy;
  }

  // ═══════════════════════════════════════════════════════════
  // 控件：Slider
  // ═══════════════════════════════════════════════════════════
  // 工具：根据 step 推断「优雅」的小数位数，避免整数滑块显示成 1.00
  function _decimalsOf(step) {
    if (!isFinite(step) || step <= 0) return 2;
    if (step >= 1) return 0;
    const s = step.toString();
    if (s.indexOf("e-") >= 0) return parseInt(s.split("e-")[1], 10);
    const dot = s.indexOf(".");
    return dot < 0 ? 0 : Math.min(s.length - dot - 1, 6);
  }
  // 工具：未指定 step 时给一个 10 的整次幂步长（如 0.01 / 0.1 / 1）
  function _autoStep(min, max) {
    const range = Math.abs(max - min) || 1;
    const mag = Math.pow(10, Math.floor(Math.log10(range / 100)));
    return mag;
  }

  function createSlider(name, opts = {}) {
    const {
      min = 0,
      max = 1,
      default: def = min,
      label,
      unit,
      showValue = true,
    } = opts;
    const step = opts.step != null ? opts.step : _autoStep(min, max);
    const decimals = _decimalsOf(step);
    const fmt = (v) => v.toFixed(decimals) + (unit ? " " + unit : "");
    let value = def;
    const cbs = [];

    const wrap = el("div", {
      display: "flex",
      flexDirection: "column",
      gap: "4px",
      minWidth: "140px",
      flex: "1",
      maxWidth: "240px",
    });
    const row = el("div", {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
    });
    const lbl = el(
      "span",
      { fontSize: "11px", color: "var(--ev-text-sec)", fontWeight: "500" },
      [label || name],
    );
    const val = el(
      "span",
      { fontSize: "11px", color: "var(--ev-brand)", fontFamily: "monospace" },
      [fmt(value)],
    );
    row.append(lbl);
    if (showValue) row.append(val);

    const input = document.createElement("input");
    Object.assign(input, { type: "range", min, max, step, value });
    input.className = "ev-slider-track";

    input.addEventListener("input", (e) => {
      value = parseFloat(e.target.value);
      if (showValue) val.textContent = fmt(value);
      cbs.forEach((fn) => {
        try {
          fn(value);
        } catch (e2) {
          console.error("[EduViz] slider onChange error:", e2);
        }
      });
    });

    wrap.append(row, input);
    _state.controlsEl.appendChild(wrap);

    const ctrl = {
      get value() {
        return value;
      },
      get min() {
        return parseFloat(input.min);
      },
      set min(v) {
        input.min = v;
        if (value < v) ctrl.setValue(v);
      },
      get max() {
        return parseFloat(input.max);
      },
      set max(v) {
        input.max = v;
        if (value > v) ctrl.setValue(v);
      },
      get step() {
        return parseFloat(input.step);
      },
      set step(v) {
        input.step = v;
      },
      onChange(fn) {
        cbs.push(fn);
        try {
          fn(value);
        } catch (e) {
          console.error("[EduViz] slider onChange init error:", e);
        }
        return ctrl;
      },
      setValue(v) {
        value = v;
        input.value = v;
        if (showValue) val.textContent = fmt(v);
        cbs.forEach((fn) => {
          try {
            fn(v);
          } catch (e) {
            console.error("[EduViz] slider onChange error:", e);
          }
        });
        return ctrl;
      },
    };
    notifyResize();
    return ctrl;
  }

  // ═══════════════════════════════════════════════════════════
  // 控件：Timeline（播放/暂停 + 进度条）
  // ═══════════════════════════════════════════════════════════
  function createTimeline(opts = {}) {
    const { fps = 30, loop = false, autoPlay = false } = opts;
    let duration = opts.duration !== undefined ? opts.duration : 5;
    let time = 0,
      playing = false,
      lastTs = null,
      frameId = null;
    const cbs = [];

    const wrap = el("div", {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "8px 12px",
      background: "var(--ev-panel)",
      borderRadius: "8px",
      border: "1px solid var(--ev-border)",
      width: "100%",
    });
    const btn = el(
      "button",
      {
        width: "28px",
        height: "28px",
        borderRadius: "50%",
        border: "none",
        background: "var(--ev-brand)",
        color: "#fff",
        cursor: "pointer",
        fontSize: "12px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      },
      ["▶"],
    );
    const bar = el("div", {
      flex: "1",
      height: "4px",
      background: "var(--ev-track)",
      borderRadius: "2px",
      position: "relative",
      cursor: "pointer",
    });
    const fill = el("div", {
      height: "100%",
      background: "var(--ev-brand)",
      borderRadius: "2px",
      width: "0%",
    });
    bar.appendChild(fill);
    const tEl = el(
      "span",
      {
        fontSize: "11px",
        color: "var(--ev-text-sec)",
        fontFamily: "monospace",
      },
      ["0.00s"],
    );

    function tick(ts) {
      if (!playing) return;
      if (!lastTs) lastTs = ts;
      const dt = Math.min((ts - lastTs) / 1000, 1 / fps);
      lastTs = ts;
      time += dt;
      if (time >= duration) {
        if (loop) time = 0;
        else {
          time = duration;
          ctrl.pause();
          return;
        }
      }
      fill.style.width = (time / duration) * 100 + "%";
      tEl.textContent = time.toFixed(2) + "s";
      cbs.forEach((fn) => {
        try {
          fn(time, dt);
        } catch (e) {
          console.error("[EduViz] onFrame error:", e);
        }
      });
      frameId = requestAnimationFrame(tick);
    }

    btn.onclick = () => {
      if (playing) ctrl.pause();
      else ctrl.play();
    };
    bar.onclick = (e) => {
      const r = bar.getBoundingClientRect();
      ctrl.seek(((e.clientX - r.left) / r.width) * duration);
    };
    wrap.append(btn, bar, tEl);
    _state.controlsEl.appendChild(wrap);

    const ctrl = {
      // getter 保证外部读到的总是最新值，避免手动同步遗漏
      get time() {
        return time;
      },
      get playing() {
        return playing;
      },
      get duration() {
        return duration;
      },
      set duration(v) {
        duration = Math.max(0.01, v);
        if (time > duration) ctrl.seek(duration);
      },
      // 注册时立即用 t=0 触发一次，确保暂停态首屏就能看到画面（而不是空白）
      onFrame(fn) {
        cbs.push(fn);
        try {
          fn(0, 0);
        } catch (e) {
          console.error("[EduViz] onFrame init error:", e);
        }
        return ctrl;
      },
      play() {
        if (playing) return ctrl;
        playing = true;
        lastTs = null;
        btn.textContent = "⏸";
        frameId = requestAnimationFrame(tick);
        return ctrl;
      },
      pause() {
        playing = false;
        btn.textContent = "▶";
        if (frameId) {
          cancelAnimationFrame(frameId);
          frameId = null;
        }
        return ctrl;
      },
      reset() {
        ctrl.pause();
        time = 0;
        fill.style.width = "0%";
        tEl.textContent = "0.00s";
        cbs.forEach((fn) => {
          try {
            fn(0, 0);
          } catch (e) {
            console.error("[EduViz] onFrame error:", e);
          }
        });
        return ctrl;
      },
      seek(t) {
        time = Math.max(0, Math.min(t, duration));
        fill.style.width = (time / duration) * 100 + "%";
        tEl.textContent = time.toFixed(2) + "s";
        cbs.forEach((fn) => {
          try {
            fn(time, 0);
          } catch (e) {
            console.error("[EduViz] onFrame error:", e);
          }
        });
        return ctrl;
      },
    };
    if (autoPlay) setTimeout(() => ctrl.play(), 100);
    notifyResize();
    return ctrl;
  }

  // ═══════════════════════════════════════════════════════════
  // 控件：Stepper（步进器）
  // ═══════════════════════════════════════════════════════════
  function createStepper(opts = {}) {
    const { label = "步骤", autoPlay = false } = opts;
    let total = opts.total !== undefined ? opts.total : 10;
    let interval = opts.interval !== undefined ? opts.interval : 800;
    let step = 0,
      timerId = null;
    const cbs = [];

    const wrap = el("div", {
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "8px 12px",
      background: "var(--ev-panel)",
      borderRadius: "8px",
      border: "1px solid var(--ev-border)",
      width: "100%",
    });
    const bs = {
      width: "26px",
      height: "26px",
      borderRadius: "4px",
      border: "1px solid var(--ev-border)",
      background: "transparent",
      color: "var(--ev-text)",
      cursor: "pointer",
      fontSize: "11px",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    };
    const prevBtn = el("button", bs, ["◀"]);
    const playBtn = el(
      "button",
      { ...bs, background: "var(--ev-brand)", color: "#fff", border: "none" },
      ["▶"],
    );
    const nextBtn = el("button", bs, ["▶|"]);
    const info = el(
      "span",
      {
        fontSize: "11px",
        color: "var(--ev-text-sec)",
        fontFamily: "monospace",
        marginLeft: "auto",
      },
      [`${label}: 0 / ${total - 1}`],
    );

    function update() {
      info.textContent = `${label}: ${step} / ${total - 1}`;
      cbs.forEach((fn) => {
        try {
          fn(step);
        } catch (e) {
          console.error("[EduViz] onStep error:", e);
        }
      });
    }
    prevBtn.onclick = () => ctrl.prev();
    nextBtn.onclick = () => ctrl.next();
    playBtn.onclick = () => {
      if (timerId) ctrl.pause();
      else ctrl.play();
    };
    wrap.append(prevBtn, playBtn, nextBtn, info);
    _state.controlsEl.appendChild(wrap);

    const ctrl = {
      // getter 同 timeline，保证外部读实时值
      get step() {
        return step;
      },
      get total() {
        return total;
      },
      set total(v) {
        total = Math.max(1, v | 0);
        step = Math.min(step, total - 1);
        info.textContent = `${label}: ${step} / ${total - 1}`;
      },
      get interval() {
        return interval;
      },
      set interval(v) {
        interval = Math.max(50, v | 0);
        if (timerId) {
          ctrl.pause();
          ctrl.play();
        }
      },
      onStep(fn) {
        cbs.push(fn);
        try {
          fn(step);
        } catch (e) {
          console.error("[EduViz] onStep init error:", e);
        }
        return ctrl;
      },
      next() {
        if (step < total - 1) {
          step++;
          update();
        } else if (timerId) ctrl.pause();
        return ctrl;
      },
      prev() {
        if (step > 0) {
          step--;
          update();
        }
        return ctrl;
      },
      goto(s) {
        step = Math.max(0, Math.min(s | 0, total - 1));
        update();
        return ctrl;
      },
      reset() {
        ctrl.pause();
        step = 0;
        update();
        return ctrl;
      },
      play() {
        if (timerId) return ctrl; // 已在播放，避免重复创建定时器造成泄露
        playBtn.textContent = "⏸";
        timerId = setInterval(() => ctrl.next(), interval);
        return ctrl;
      },
      pause() {
        playBtn.textContent = "▶";
        if (timerId) {
          clearInterval(timerId);
          timerId = null;
        }
        return ctrl;
      },
    };
    if (autoPlay) setTimeout(() => ctrl.play(), 100);
    notifyResize();
    return ctrl;
  }

  // ═══════════════════════════════════════════════════════════
  // 控件：Toggle / Select / Button
  // ═══════════════════════════════════════════════════════════
  function createToggle(name, opts = {}) {
    const { default: def = false, label } = opts;
    let value = def;
    const cbs = [];
    const wrap = el("div", {
      display: "flex",
      alignItems: "center",
      gap: "8px",
    });
    const lbl = el("span", { fontSize: "11px", color: "var(--ev-text-sec)" }, [
      label || name,
    ]);
    const tog = el("div", {
      width: "32px",
      height: "18px",
      borderRadius: "9px",
      cursor: "pointer",
      background: value ? "var(--ev-brand)" : "var(--ev-track)",
      transition: "background 0.2s",
      position: "relative",
    });
    const knob = el("div", {
      width: "14px",
      height: "14px",
      borderRadius: "50%",
      background: "#fff",
      position: "absolute",
      top: "2px",
      left: value ? "16px" : "2px",
      transition: "left 0.2s",
    });
    tog.appendChild(knob);
    function _paint() {
      tog.style.background = value ? "var(--ev-brand)" : "var(--ev-track)";
      knob.style.left = value ? "16px" : "2px";
    }
    tog.onclick = () => {
      value = !value;
      _paint();
      cbs.forEach((fn) => {
        try {
          fn(value);
        } catch (e) {
          console.error("[EduViz] toggle onChange error:", e);
        }
      });
    };
    wrap.append(lbl, tog);
    _state.controlsEl.appendChild(wrap);
    const ctrl = {
      get value() {
        return value;
      },
      onChange(fn) {
        cbs.push(fn);
        try {
          fn(value);
        } catch (e) {
          console.error("[EduViz] toggle onChange init error:", e);
        }
        return ctrl;
      },
      setValue(v) {
        value = !!v;
        _paint();
        cbs.forEach((fn) => {
          try {
            fn(value);
          } catch (e) {
            console.error("[EduViz] toggle onChange error:", e);
          }
        });
        return ctrl;
      },
    };
    notifyResize();
    return ctrl;
  }

  function createSelect(name, opts = {}) {
    const { choices = [], default: def, label } = opts;
    let value = def || (choices[0] && choices[0].value) || "";
    const cbs = [];
    const wrap = el("div", {
      display: "flex",
      alignItems: "center",
      gap: "8px",
    });
    const lbl = el("span", { fontSize: "11px", color: "var(--ev-text-sec)" }, [
      label || name,
    ]);
    const sel = document.createElement("select");
    Object.assign(sel.style, {
      padding: "4px 8px",
      borderRadius: "4px",
      fontSize: "12px",
      background: "var(--ev-panel)",
      color: "var(--ev-text)",
      border: "1px solid var(--ev-border)",
      cursor: "pointer",
    });
    choices.forEach((ch) => {
      const o = document.createElement("option");
      o.value = ch.value;
      o.textContent = ch.label;
      if (ch.value === value) o.selected = true;
      sel.appendChild(o);
    });
    sel.onchange = (e) => {
      value = e.target.value;
      cbs.forEach((fn) => {
        try {
          fn(value);
        } catch (e2) {
          console.error("[EduViz] select onChange error:", e2);
        }
      });
    };
    wrap.append(lbl, sel);
    _state.controlsEl.appendChild(wrap);
    const ctrl = {
      get value() {
        return value;
      },
      onChange(fn) {
        cbs.push(fn);
        try {
          fn(value);
        } catch (e) {
          console.error("[EduViz] select onChange init error:", e);
        }
        return ctrl;
      },
      setValue(v) {
        value = v;
        sel.value = v;
        cbs.forEach((fn) => {
          try {
            fn(value);
          } catch (e) {
            console.error("[EduViz] select onChange error:", e);
          }
        });
        return ctrl;
      },
      setChoices(newChoices) {
        sel.innerHTML = "";
        newChoices.forEach((ch) => {
          const o = document.createElement("option");
          o.value = ch.value;
          o.textContent = ch.label;
          sel.appendChild(o);
        });
        const firstVal = newChoices[0] && newChoices[0].value;
        value = newChoices.find((c) => c.value === value)
          ? value
          : firstVal || "";
        sel.value = value;
        return ctrl;
      },
    };
    notifyResize();
    return ctrl;
  }

  function createButton(label, opts = {}) {
    const { variant = "default" } = opts;
    const cbs = [];
    // variant: 'primary' | 'default' | 'success' | 'warning' | 'danger'
    const variantBg = {
      primary: "var(--ev-brand)",
      success: "var(--ev-success)",
      warning: "var(--ev-warning)",
      danger: "var(--ev-danger)",
    };
    function _applyVariant(v) {
      const isFilled = !!variantBg[v];
      btn.style.border = isFilled ? "none" : "1px solid var(--ev-border)";
      btn.style.background = isFilled ? variantBg[v] : "transparent";
      btn.style.color = isFilled ? "#fff" : "var(--ev-text)";
    }
    const btn = el(
      "button",
      {
        padding: "6px 14px",
        borderRadius: "6px",
        fontSize: "12px",
        fontWeight: "500",
        cursor: "pointer",
      },
      [label],
    );
    _applyVariant(variant);
    btn.onclick = () => {
      if (btn.disabled) return;
      cbs.forEach((fn) => {
        try {
          fn();
        } catch (e) {
          console.error("[EduViz] button onClick error:", e);
        }
      });
    };
    _state.controlsEl.appendChild(btn);
    notifyResize(); // 修复：button 创建后也需通知父容器更新高度
    const ctrl = {
      onClick(fn) {
        cbs.push(fn);
        return ctrl;
      },
      setLabel(t) {
        btn.textContent = t;
        return ctrl;
      },
      setDisabled(d) {
        btn.disabled = !!d;
        btn.style.opacity = d ? "0.45" : "1";
        btn.style.cursor = d ? "not-allowed" : "pointer";
        return ctrl;
      },
      setVariant(v) {
        _applyVariant(v);
        return ctrl;
      },
      get el() {
        return btn;
      },
    };
    return ctrl;
  }

  // ═══════════════════════════════════════════════════════════
  // 布局辅助：获取可视化容器 / 创建 Canvas
  // ═══════════════════════════════════════════════════════════
  function getContainer() {
    return _state.vizEl;
  }

  function createCanvas(width, height) {
    const canvas = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1;
    const cssW = width || _state.vizEl.clientWidth || 500;
    const cssH = height && height > 0 ? height : 300;
    const w = cssW > 0 ? cssW : 500;
    // 物理像素 = CSS 像素 × dpr，避免 Retina 屏模糊
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas.style.cssText = `width:${w}px;height:${cssH}px;border-radius:8px;display:block;max-width:100%;`;
    // 把 dpr 挂在 canvas 上，方便 axis2d 等读取
    canvas._dpr = dpr;
    const ctx = canvas.getContext("2d");
    if (ctx) ctx.scale(dpr, dpr);
    _state.vizEl.appendChild(canvas);
    notifyResize();
    return canvas;
  }

  // ═══════════════════════════════════════════════════════════
  // 反馈控件：Metric（大数字徽标） / Progress（进度条） / Badge（状态标签）
  // ═══════════════════════════════════════════════════════════
  // 合法语义色名单调校验（避免 setColor('red') 静默失效）
  const _SEMANTIC_COLORS = [
    "brand",
    "success",
    "warning",
    "danger",
    "info",
    "text",
  ];
  function _resolveSemanticColor(c, fallback = "brand") {
    if (!c) return `var(--ev-${fallback})`;
    if (c === "text") return "var(--ev-text)";
    if (_SEMANTIC_COLORS.indexOf(c) >= 0) return `var(--ev-${c})`;
    // 接受 CSS 直接色值（#hex / rgb() / hsl() / 命名色）
    if (c[0] === "#" || c.indexOf("rgb") === 0 || c.indexOf("hsl") === 0)
      return c;
    console.warn(
      `[EduViz] 未知颜色 "${c}"，请使用语义色名 (${_SEMANTIC_COLORS.join("|")}) 或 CSS 色值，已回退为 ${fallback}`,
    );
    return `var(--ev-${fallback})`;
  }

  /**
   * 大号数字展示，用于实时反馈关键指标（如「斜率 = 2.50」「能量 = 12.3 J」）
   * @param {string} label - 左侧标签
   * @param {object} opts  - { value, unit, color }, color: 'brand'|'success'|'warning'|'danger'|'info'|'text'
   */
  function createMetric(label, opts = {}) {
    const { value = "—", unit = "", color = "brand" } = opts;
    const wrap = el("div", {
      display: "flex",
      alignItems: "baseline",
      gap: "8px",
      padding: "8px 12px",
      background: "var(--ev-panel)",
      border: "1px solid var(--ev-border)",
      borderRadius: "8px",
    });
    const lblEl = el(
      "span",
      { fontSize: "11px", color: "var(--ev-text-sec)", fontWeight: "500" },
      [label],
    );
    const valEl = el(
      "span",
      {
        fontSize: "20px",
        fontFamily: "monospace",
        fontWeight: "600",
        color: _resolveSemanticColor(color),
      },
      [String(value)],
    );
    const unitEl = el(
      "span",
      { fontSize: "12px", color: "var(--ev-text-sec)" },
      [unit],
    );
    wrap.append(lblEl, valEl, unitEl);
    _state.infoEl.appendChild(wrap);
    notifyResize();
    return {
      set(v, u) {
        valEl.textContent = v == null ? "—" : String(v);
        if (u !== undefined) unitEl.textContent = u;
        return this;
      },
      setColor(c) {
        valEl.style.color = _resolveSemanticColor(c);
        return this;
      },
    };
  }

  /**
   * 进度条，用于显示「已完成比例」「相似度」等 0-100% 量
   * @param {string} label
   * @param {object} opts - { value=0, max=1, color='brand', showText=true }
   */
  function createProgress(label, opts = {}) {
    const { value = 0, max = 1, color = "brand", showText = true } = opts;
    const colorCss = _resolveSemanticColor(color);
    const wrap = el("div", {
      display: "flex",
      flexDirection: "column",
      gap: "4px",
    });
    const row = el("div", {
      display: "flex",
      justifyContent: "space-between",
      fontSize: "11px",
    });
    const lblEl = el("span", { color: "var(--ev-text-sec)" }, [label]);
    const txtEl = el("span", { color: colorCss, fontFamily: "monospace" });
    row.append(lblEl);
    if (showText) row.append(txtEl);
    const bar = el("div", {
      height: "6px",
      background: "var(--ev-track)",
      borderRadius: "3px",
      overflow: "hidden",
    });
    const fill = el("div", {
      height: "100%",
      background: colorCss,
      transition: "width 0.18s ease",
      width: "0%",
    });
    bar.appendChild(fill);
    wrap.append(row, bar);
    _state.infoEl.appendChild(wrap);
    function paint(v) {
      const safe = isFinite(v) ? v : 0;
      const pct = Math.max(0, Math.min(1, safe / (max || 1))) * 100;
      fill.style.width = pct.toFixed(1) + "%";
      if (showText) txtEl.textContent = pct.toFixed(0) + "%";
    }
    paint(value);
    notifyResize();
    return {
      set(v) {
        paint(v);
        return this;
      },
      setColor(c) {
        const css = _resolveSemanticColor(c);
        fill.style.background = css;
        txtEl.style.color = css;
        return this;
      },
    };
  }

  // ═══════════════════════════════════════════════════════════
  // 展示辅助：LaTeX / Text
  // ═══════════════════════════════════════════════════════════
  function createLatex(expr, opts = {}) {
    const { displayMode = true, fontSize = 16 } = opts;
    const div = el("div", {
      textAlign: "center",
      padding: "8px",
      fontSize: fontSize + "px",
      color: "var(--ev-text)",
      minHeight: "24px",
    });
    function render(e) {
      let s = e == null ? "" : String(e).trim();
      // 自动剥离首尾的 $$ 或 $，兼容用户传入带定界符的 LaTeX
      if (s.startsWith("$$") && s.endsWith("$$")) {
        s = s.slice(2, -2).trim();
      } else if (s.startsWith("$") && s.endsWith("$")) {
        s = s.slice(1, -1).trim();
      }
      if (window.katex) {
        try {
          div.innerHTML = window.katex.renderToString(s, {
            displayMode,
            throwOnError: false,
          });
        } catch {
          div.textContent = s;
        }
      } else div.textContent = s;
      notifyResize();
    }
    // 先 append 再 render，确保 notifyResize 上报高度时 div 已在 DOM 中
    _state.infoEl.appendChild(div);
    render(expr);
    return { set: render };
  }

  function createText(content) {
    const div = el(
      "div",
      { fontSize: "13px", color: "var(--ev-text)", lineHeight: "1.6" },
      [content],
    );
    _state.infoEl.appendChild(div);
    notifyResize();
    return {
      set(t) {
        div.textContent = t;
        notifyResize();
      },
    };
  }

  // ═══════════════════════════════════════════════════════════
  // 主题切换通信
  // ═══════════════════════════════════════════════════════════
  const _themeWatchers = [];
  function onThemeChange(fn) {
    _themeWatchers.push(fn);
    return () => {
      const i = _themeWatchers.indexOf(fn);
      if (i >= 0) _themeWatchers.splice(i, 1);
    };
  }

  function notifyThemeChange() {
    const c = colors();
    _themeWatchers.forEach((fn) => {
      try {
        fn(_state.theme, c);
      } catch (e) {
        console.error("[EduViz] theme watcher error:", e);
      }
    });
  }

  window.addEventListener("message", (e) => {
    const msg = e.data;
    if (msg && msg.type === "theme") {
      const old = _state.theme;
      _state.theme = msg.theme;
      applyThemeToBody();
      if (old !== msg.theme) notifyThemeChange();
    }
  });

  // ═══════════════════════════════════════════════════════════
  // 坐标系辅助：Axis2D（针对 Canvas 2D 的 2D 函数/几何绘图）
  // 让 LLM 不必手写 toX/toY 转换、坐标轴、网格、曲线采样
  // ═══════════════════════════════════════════════════════════
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} opts - { xRange:[a,b], yRange:[a,b], showGrid=true, showAxis=true, padding=40 }
   */
  function createAxis2D(canvas, opts = {}) {
    const ctx = canvas.getContext("2d");
    // 如果 canvas 不是由 createCanvas 创建的（没有 _dpr），这里自动处理 dpr
    if (!canvas._dpr) {
      const dpr = window.devicePixelRatio || 1;
      if (dpr !== 1) {
        const cssW = canvas.width,
          cssH = canvas.height;
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
        canvas.style.width = cssW + "px";
        canvas.style.height = cssH + "px";
        ctx.scale(dpr, dpr);
      }
      canvas._dpr = window.devicePixelRatio || 1;
    }
    const cfg = {
      xRange: opts.xRange || [-5, 5],
      yRange: opts.yRange || [-5, 5],
      showGrid: opts.showGrid !== false,
      showAxis: opts.showAxis !== false,
      padding: opts.padding != null ? opts.padding : 40,
    };
    // dpr 已在 createCanvas 里通过 ctx.scale(dpr,dpr) 处理，
    // 所以 ctx 的逻辑坐标空间就是 CSS 像素，这里用 CSS 尺寸计算
    const dpr = canvas._dpr || 1;
    function W() {
      return canvas.width / dpr;
    }
    function H() {
      return canvas.height / dpr;
    }
    function toX(x) {
      const p = cfg.padding;
      return (
        p +
        ((x - cfg.xRange[0]) / (cfg.xRange[1] - cfg.xRange[0])) * (W() - 2 * p)
      );
    }
    function toY(y) {
      const p = cfg.padding;
      return (
        H() -
        p -
        ((y - cfg.yRange[0]) / (cfg.yRange[1] - cfg.yRange[0])) * (H() - 2 * p)
      );
    }
    // 估算「优雅刻度」：5~10 根线
    function _ticks(min, max) {
      let lo = min,
        hi = max;
      if (hi < lo) {
        const t = lo;
        lo = hi;
        hi = t;
      } // 允许逆序范围
      const range = hi - lo;
      if (!isFinite(range) || range <= 0) {
        // 退化：仅返回中点一个刻度，避免 step=0 死循环
        return { ticks: [lo], step: 1 };
      }
      const raw = range / 8;
      const mag = Math.pow(10, Math.floor(Math.log10(raw)));
      const norm = raw / mag;
      const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
      if (!isFinite(step) || step <= 0) return { ticks: [lo], step: 1 };
      const ticks = [];
      const start = Math.ceil(lo / step) * step;
      // 额外限制总迭代次数，双保险
      const maxIter = 200;
      let v = start,
        n = 0;
      while (v <= hi + 1e-9 && n++ < maxIter) {
        ticks.push(Math.round(v / step) * step);
        v += step;
      }
      return { ticks, step };
    }
    function clear() {
      ctx.clearRect(0, 0, W(), H());
    }
    function drawAxes() {
      const c = colors();
      const xT = _ticks(cfg.xRange[0], cfg.xRange[1]);
      const yT = _ticks(cfg.yRange[0], cfg.yRange[1]);
      // 网格
      if (cfg.showGrid) {
        ctx.save();
        ctx.strokeStyle = c.border;
        ctx.lineWidth = 1;
        xT.ticks.forEach((x) => {
          ctx.beginPath();
          ctx.moveTo(toX(x), toY(cfg.yRange[0]));
          ctx.lineTo(toX(x), toY(cfg.yRange[1]));
          ctx.stroke();
        });
        yT.ticks.forEach((y) => {
          ctx.beginPath();
          ctx.moveTo(toX(cfg.xRange[0]), toY(y));
          ctx.lineTo(toX(cfg.xRange[1]), toY(y));
          ctx.stroke();
        });
        ctx.restore();
      }
      if (cfg.showAxis) {
        ctx.save();
        ctx.strokeStyle = c.textSec;
        ctx.lineWidth = 1.2;
        ctx.fillStyle = c.textSec;
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        // x 轴 (y=0 或最低)
        const y0 = cfg.yRange[0] <= 0 && cfg.yRange[1] >= 0 ? 0 : cfg.yRange[0];
        ctx.beginPath();
        ctx.moveTo(toX(cfg.xRange[0]), toY(y0));
        ctx.lineTo(toX(cfg.xRange[1]), toY(y0));
        ctx.stroke();
        xT.ticks.forEach((x) => {
          ctx.fillText(_fmtTick(x, xT.step), toX(x), toY(y0) + 4);
        });
        // y 轴
        const x0 = cfg.xRange[0] <= 0 && cfg.xRange[1] >= 0 ? 0 : cfg.xRange[0];
        ctx.beginPath();
        ctx.moveTo(toX(x0), toY(cfg.yRange[0]));
        ctx.lineTo(toX(x0), toY(cfg.yRange[1]));
        ctx.stroke();
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        yT.ticks.forEach((y) => {
          if (Math.abs(y) > 1e-9)
            ctx.fillText(_fmtTick(y, yT.step), toX(x0) - 4, toY(y));
        });
        ctx.restore();
      }
    }
    function _fmtTick(v, step) {
      const d = _decimalsOf(step);
      return d === 0 ? Math.round(v).toString() : v.toFixed(d);
    }
    function _resolveColor(name) {
      const c = colors();
      if (!name) return c.brand;
      if (
        name[0] === "#" ||
        name.indexOf("rgb") === 0 ||
        name.indexOf("hsl") === 0
      )
        return name;
      return c[name] || c.brand;
    }
    /** 绘制函数曲线 y = f(x) */
    function plot(fn, opts2 = {}) {
      const color = _resolveColor(opts2.color);
      const lineWidth = opts2.width || 2;
      const samples = opts2.samples || 200;
      const dash = opts2.dash || null;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      if (dash) ctx.setLineDash(dash);
      ctx.beginPath();
      let started = false;
      for (let i = 0; i <= samples; i++) {
        const x =
          cfg.xRange[0] + (cfg.xRange[1] - cfg.xRange[0]) * (i / samples);
        let y;
        try {
          y = fn(x);
        } catch {
          started = false;
          continue;
        } // 抛错同样要断开路径
        if (!isFinite(y)) {
          started = false;
          continue;
        }
        const py = toY(y),
          px = toX(x);
        if (!started) {
          ctx.moveTo(px, py);
          started = true;
        } else {
          ctx.lineTo(px, py);
        }
      }
      ctx.stroke();
      ctx.restore();
    }
    /** 标记一个点（默认 brand 实心圆） */
    function point(x, y, opts2 = {}) {
      const color = _resolveColor(opts2.color);
      const r = opts2.radius || 5;
      ctx.save();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(toX(x), toY(y), r, 0, Math.PI * 2);
      ctx.fill();
      if (opts2.label) {
        ctx.fillStyle = colors().text;
        ctx.font = "11px monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        ctx.fillText(opts2.label, toX(x) + r + 2, toY(y) - 2);
      }
      ctx.restore();
    }
    /** 绘制线段 */
    function line(p1, p2, opts2 = {}) {
      const color = _resolveColor(opts2.color);
      const lineWidth = opts2.width || 2;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      if (opts2.dash) ctx.setLineDash(opts2.dash);
      ctx.beginPath();
      ctx.moveTo(toX(p1[0]), toY(p1[1]));
      ctx.lineTo(toX(p2[0]), toY(p2[1]));
      ctx.stroke();
      ctx.restore();
    }
    /** 一键重绘：先 clear → 画轴 → 用户回调画内容 */
    function redraw(userDraw) {
      clear();
      drawAxes();
      if (typeof userDraw === "function") userDraw(api);
    }
    const api = {
      ctx,
      canvas,
      toX,
      toY,
      plot,
      point,
      line,
      clear,
      drawAxes,
      redraw,
      setRange(xR, yR) {
        if (xR) cfg.xRange = xR;
        if (yR) cfg.yRange = yR;
        return api;
      },
    };
    return api;
  }

  // ═══════════════════════════════════════════════════════════
  // 暴露全局 API
  // ═══════════════════════════════════════════════════════════
  window.EduViz = {
    // 第三方库加载
    loadLib,

    // 控件
    slider: createSlider,
    timeline: createTimeline,
    stepper: createStepper,
    toggle: createToggle,
    select: createSelect,
    button: createButton,

    // 响应式状态
    state,

    // 布局
    getContainer,
    createCanvas,

    // 展示
    latex: createLatex,
    text: createText,
    metric: createMetric,
    progress: createProgress,

    // 坐标系辅助（Canvas 2D）
    axis2d: createAxis2D,

    // 主题
    colors,
    onThemeChange,
    setTheme(t) {
      const old = _state.theme;
      _state.theme = t;
      applyThemeToBody();
      if (old !== t) notifyThemeChange();
    },
  };

  // ═══════════════════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════════════════
  // SDK 以内联 script 形式注入到 <body> 中，执行时 document.body 已存在，
  // 直接同步初始化，确保用户代码执行前 controlsEl / vizEl 已就绪。
  initLayout();
})();
