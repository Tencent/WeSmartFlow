/**
 * 沙箱 HTML 模板 v3
 * 主题和用户代码在构建时直接内联，无需 postMessage init 握手
 */

export const SANDBOX_HTML =
  `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EduViz Sandbox</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <scr` +
  `ipt src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></scr` +
  `ipt>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: auto !important; overflow: visible !important; }
    body { font-family: Inter, -apple-system, sans-serif; }
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
    input[type="range"] { -webkit-appearance: none; appearance: none; }
    input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none; appearance: none;
      width: 14px; height: 14px; border-radius: 50%;
      background: #6366f1; cursor: pointer; margin-top: -5px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
    }
    input[type="range"]::-webkit-slider-runnable-track { height: 4px; border-radius: 2px; }
    .ev-error {
      padding: 12px 16px; margin: 8px 0;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      border-radius: 8px; color: #ef4444;
      font-size: 12px; font-family: monospace;
      white-space: pre-wrap; word-break: break-all;
    }
    /* p5.js canvas 样式 */
    canvas { border-radius: 8px; display: block; }
    /* SVG 内容超出 viewBox 时不裁剪，避免动态内容被截断 */
    svg { overflow: visible; }
  </style>
</head>
<body>
  __EDUVIZ_SDK_PLACEHOLDER__
  <scr` +
  `ipt>
    // 主题在构建时内联，直接设置，无需等待 postMessage
    document.documentElement.setAttribute('data-theme', '__THEME__');
    if (window.EduViz && typeof window.EduViz.setTheme === 'function') {
      window.EduViz.setTheme('__THEME__');
    }

    // 监听主题切换（父页面 dark/light 切换时触发）
    window.addEventListener('message', function(event) {
      var msg = event.data;
      if (msg && msg.type === 'theme') {
        document.documentElement.setAttribute('data-theme', msg.theme);
        if (window.EduViz && typeof window.EduViz.setTheme === 'function') {
          window.EduViz.setTheme(msg.theme);
        }
      }
    });

    // 全局错误捕获：静默处理，不在页面上显示红色错误块
    window.onerror = function(msg, url, line, col, err) {
      console.warn('[EduViz]', msg, err);
      return true; // 阻止默认错误显示
    };
    window.onunhandledrejection = function(event) {
      console.warn('[EduViz] Unhandled rejection:', event.reason);
      event.preventDefault();
    };

    // 用户代码在构建时内联，直接执行，支持 await EduViz.loadLib(...)
    (async function() {
      __USER_CODE__
    })().catch(function(err) {
      console.warn('[EduViz] 代码执行异常:', err.message, err.stack || '');
      // 不再在页面上显示红色错误块，仅通知父页面（父页面也不会显示）
      // window.parent.postMessage({ type: 'error', message: err.message }, '*');
    });

    // 尺寸上报：内容渲染完成后通知父页面实际宽高
    (function() {
      function report() {
        var w = document.documentElement.scrollWidth || document.body.scrollWidth;
        var h = document.documentElement.scrollHeight || document.body.scrollHeight;
        if (w > 0 && h > 0) {
          window.parent.postMessage({ type: 'resize', width: w, height: h }, '*');
        }
      }
      window.addEventListener('load', function() { setTimeout(report, 200); });
      var t;
      new MutationObserver(function() { clearTimeout(t); t = setTimeout(report, 150); })
        .observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
    })();
  </scr` +
  `ipt>
</body>
</html>`;
