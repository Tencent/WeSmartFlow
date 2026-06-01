// EduViz 可视化代码静态校验配置
// 仅启用 "运行时必炸" 的规则，避免误报阻塞 Agent
import globals from "../../../../frontend/node_modules/globals/index.js";

export default [
  {
    languageOptions: {
      ecmaVersion: "latest",
      // 校验前会把用户代码包到 (async function(){ ... })() 里，
      // 这样 sourceType: "script" 也能允许顶层 await（实际是函数内的 await）。
      sourceType: "script",
      globals: {
        ...globals.browser,
        // EduViz SDK 暴露的全局对象
        EduViz: "readonly",
        // SDK loadLib() 注册到 window 的库
        d3: "readonly",
        p5: "readonly",
        THREE: "readonly",
        Plotly: "readonly",
        Chart: "readonly",
        Matter: "readonly",
        Tone: "readonly",
        math: "readonly",
        anime: "readonly",
        katex: "readonly",
        cytoscape: "readonly",
      },
      parserOptions: {
        ecmaFeatures: { globalReturn: true },
      },
    },
    rules: {
      // 引用未定义变量 → 跑起来必炸
      "no-undef": "error",
      // 同名重复声明 → SyntaxError
      "no-redeclare": "error",
      // const 被赋值 → TypeError
      "no-const-assign": "error",
      // 函数重复参数 → 严格模式 SyntaxError
      "no-dupe-args": "error",
      // 对象字面量重复 key
      "no-dupe-keys": "error",
      // class 重复方法
      "no-dupe-class-members": "error",
      // 用前未声明（暂时性死区）
      "no-use-before-define": ["error", { functions: false, classes: false }],
      // 不可达代码（return / throw 之后）
      "no-unreachable": "error",
      // 关掉一些纯风格类规则，避免误报
      "no-unused-vars": "off",
      "no-empty": "off",
    },
  },
];
