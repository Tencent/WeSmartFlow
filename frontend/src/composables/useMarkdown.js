/**
 * 共享的 Markdown + LaTeX 渲染工具
 * 供 ChatView 和 ImmersiveView 共用
 */
import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";

// 配置 marked
marked.setOptions({ breaks: true, gfm: true });

// 常见 LaTeX 命令白名单（用于识别"裸 LaTeX"片段）
const LATEX_COMMANDS = [
  // 结构 / 分式 / 根号 / 上下标修饰
  "frac",
  "dfrac",
  "tfrac",
  "binom",
  "sqrt",
  "overline",
  "underline",
  "hat",
  "bar",
  "vec",
  "tilde",
  "dot",
  "ddot",
  // 括号 / 分隔符
  "left",
  "right",
  "langle",
  "rangle",
  "lvert",
  "rvert",
  "lVert",
  "rVert",
  // 求和 / 积分 / 极限 / 乘积
  "sum",
  "int",
  "iint",
  "iiint",
  "oint",
  "prod",
  "lim",
  "infty",
  // 关系 / 运算
  "neq",
  "leq",
  "geq",
  "approx",
  "equiv",
  "sim",
  "cdot",
  "times",
  "div",
  "pm",
  "mp",
  "to",
  "rightarrow",
  "leftarrow",
  "Rightarrow",
  "Leftarrow",
  "in",
  "notin",
  "subset",
  "subseteq",
  "supset",
  "supseteq",
  "cup",
  "cap",
  // 希腊字母（小写）
  "alpha",
  "beta",
  "gamma",
  "delta",
  "epsilon",
  "varepsilon",
  "zeta",
  "eta",
  "theta",
  "vartheta",
  "iota",
  "kappa",
  "lambda",
  "mu",
  "nu",
  "xi",
  "pi",
  "rho",
  "sigma",
  "tau",
  "upsilon",
  "phi",
  "varphi",
  "chi",
  "psi",
  "omega",
  // 希腊字母（大写）
  "Gamma",
  "Delta",
  "Theta",
  "Lambda",
  "Xi",
  "Pi",
  "Sigma",
  "Phi",
  "Psi",
  "Omega",
  // 字体 / 文本
  "mathbb",
  "mathbf",
  "mathcal",
  "mathrm",
  "mathit",
  "mathsf",
  "text",
  "textbf",
  // 矩阵 / 环境（环境一般用 \begin，不在此处穷举，由额外规则处理）
];

const LATEX_COMMAND_RE = new RegExp(
  "\\\\(?:" + LATEX_COMMANDS.join("|") + ")\\b",
);

/**
 * 自动为"裸 LaTeX"片段补上 $...$。
 *
 * 解决 LLM 偶尔不给公式加 `$` 包裹导致 \frac、\langle 等被原样显示
 * （甚至反斜杠被 marked 吞掉变成 "rac"、"angle" 等乱字）的问题。
 *
 * 策略：
 *   1. 跳过代码块 (``` ... ```) 和行内代码 (`...`) 区域；
 *   2. 跳过已被 $...$ / $$...$$ / \(...\) / \[...\] 包裹的区域；
 *   3. 对剩余文本，识别仍裸露在外的 LaTeX 命令（\frac{..}{..}、\langle、\lambda 等），
 *      连同其相邻的运算符 / 上下标 / 大括号一起，整体用 $...$ 包裹。
 */
export function autoWrapBareLatex(text) {
  if (!text || typeof text !== "string") return text || "";
  // 如果根本不含反斜杠命令，快速返回
  if (!LATEX_COMMAND_RE.test(text)) return text;

  // ✅ 关键防御：只要文本里已经存在 $...$ / $$...$$ 包裹的公式，就放行不再兜底。
  // 这样可以避免 wrapBareLatexInLine 的索引修正在边角情况下把 $$..$$ 撕碎。
  // 规范文档（如本项目自己生成的 chapter overview md）已经全部带 $ 包裹，不需要兜底；
  // 兜底逻辑只为真正"裸 LaTeX 没有 $ 包裹"的 LLM 输出准备。
  if (/\$[^\n$]+?\$/.test(text) || /\$\$[\s\S]+?\$\$/.test(text)) {
    return text;
  }

  // 1) 先把"已保护区域"挖出来用占位符替换：代码块、行内代码、已有的公式块
  const protectedSegs = [];
  const protect = (s) => {
    const id = `\uFFFEPROT${protectedSegs.length}\uFFFE`;
    protectedSegs.push(s);
    return id;
  };

  let work = text;
  // 代码块 ```...```
  work = work.replace(/```[\s\S]*?```/g, (m) => protect(m));
  // 行内代码 `...`
  work = work.replace(/`[^`\n]+`/g, (m) => protect(m));
  // 已有块级公式 $$...$$
  work = work.replace(/\$\$[\s\S]+?\$\$/g, (m) => protect(m));
  // 已有 \[...\]
  work = work.replace(/\\\[[\s\S]+?\\\]/g, (m) => protect(m));
  // 已有 \(...\)
  work = work.replace(/\\\(.+?\\\)/g, (m) => protect(m));
  // 已有行内 $...$
  work = work.replace(/(?<!\$)\$(?!\$)[^\n$]+?(?<!\$)\$(?!\$)/g, (m) =>
    protect(m),
  );

  // 2) 对剩余文本，按行扫描，把裸 LaTeX 片段包裹
  const lines = work.split("\n");
  const wrapped = lines.map((line) => wrapBareLatexInLine(line));
  work = wrapped.join("\n");

  // 3) 还原占位符
  work = work.replace(
    /\uFFFEPROT(\d+)\uFFFE/g,
    (_, i) => protectedSegs[Number(i)] || "",
  );
  return work;
}

/**
 * 单行内识别裸 LaTeX 片段并包裹 $...$。
 * 算法：
 *   - 找到行内每一个 LaTeX 命令出现位置；
 *   - 以该位置为种子，向左/右扩展取连续的"公式相关字符"，形成最小公式片段；
 *   - 用 $...$ 包裹。
 *   - 多个命令若属于同一连续片段，会被合并。
 */
function wrapBareLatexInLine(line) {
  if (!line.includes("\\")) return line;

  // 公式相关字符集：字母、数字、运算符、上下标、大括号、希腊字母命令等
  // 只要前后是这些字符，就认为是同一个公式片段的一部分
  const formulaChar = (ch) => {
    if (!ch) return false;
    // eslint-disable-next-line no-useless-escape
    return /[A-Za-z0-9_^{}()\[\]+\-*/=<>|.,\\!:;\s]/.test(ch);
  };

  const cmdRe = new RegExp("\\\\(?:" + LATEX_COMMANDS.join("|") + ")\\b", "g");
  const matches = [];
  let m;
  while ((m = cmdRe.exec(line)) !== null) {
    matches.push({ start: m.index, end: m.index + m[0].length });
  }
  if (matches.length === 0) return line;

  // 把每个命令向两侧扩展为最小公式片段
  const segs = matches.map(({ start, end }) => {
    let s = start;
    let e = end;

    // 向右扩展：吃掉紧跟的 { ... } 参数（用括号配平）以及连续的公式字符
    while (e < line.length) {
      const ch = line[e];
      if (ch === "{") {
        // 配平大括号
        let depth = 1;
        let p = e + 1;
        while (p < line.length && depth > 0) {
          if (line[p] === "{") depth++;
          else if (line[p] === "}") depth--;
          p++;
        }
        e = p;
      } else if (formulaChar(ch) && ch !== " " && ch !== "\t") {
        e++;
      } else if (ch === " " || ch === "\t") {
        // 空格只在后面紧跟公式字符时才算"片段内"
        let p = e + 1;
        while (p < line.length && (line[p] === " " || line[p] === "\t")) p++;
        const next = line[p];
        if (
          next &&
          (next === "\\" ||
            next === "{" ||
            next === "(" ||
            /[+\-*/=<>^_]/.test(next))
        ) {
          e = p;
        } else {
          break;
        }
      } else {
        break;
      }
    }

    // 向左扩展：吃掉相邻的简短表达式（如 "p =" 中的 "p"、"= " 等）
    while (s > 0) {
      const ch = line[s - 1];
      if (/[A-Za-z0-9_^{}()+\-*/=<>|.\\]/.test(ch)) {
        s--;
      } else if (ch === " " || ch === "\t") {
        // 仅当前一个非空字符是公式相关时才继续吃
        let p = s - 1;
        while (p > 0 && (line[p - 1] === " " || line[p - 1] === "\t")) p--;
        const prev = line[p - 1];
        if (prev && /[A-Za-z0-9_^{}()+\-*/=<>|.\\]/.test(prev)) {
          s = p;
        } else {
          break;
        }
      } else {
        break;
      }
    }
    return { s, e };
  });

  // 合并重叠片段
  segs.sort((a, b) => a.s - b.s);
  const merged = [];
  for (const seg of segs) {
    if (merged.length && seg.s <= merged[merged.length - 1].e) {
      merged[merged.length - 1].e = Math.max(
        merged[merged.length - 1].e,
        seg.e,
      );
    } else {
      merged.push({ ...seg });
    }
  }

  // 反向替换，避免索引偏移
  let result = line;
  for (let i = merged.length - 1; i >= 0; i--) {
    const { s, e } = merged[i];
    let frag = result.slice(s, e).replace(/\s+$/, "");
    // 去掉左侧多余空格
    const trimLeft = frag.match(/^\s*/)[0].length;
    const realStart = s + trimLeft;
    frag = frag.slice(trimLeft);
    if (!frag) continue;
    // ✅ 后半段必须从原区间末端 e 起步（之前用 s+trimLeft+frag.length 漏算了
    // 末尾被 trim 掉的空白长度，会导致空白字符被重复/丢失，进而把后续 $$...$$
    // 边界撕碎）。
    result = result.slice(0, realStart) + "$" + frag + "$" + result.slice(e);
  }
  return result;
}

/**
 * 块级公式表达式喂给 KaTeX 之前的"健壮性兜底"清理。
 *
 * 解决 LLM 经常写出的几类问题：
 *   (a) 公式内残留字面 `\n`（来自 LLM 把换行误写成 `\n`，或 JSON 解码不彻底）
 *       → KaTeX 把 `\n` 当成未知命令，红字显示。我们直接把它替换成空格，
 *         在 LaTeX 公式语义里空格是无意义分隔，不影响排版。
 *   (b) LLM 用单大括号 `\{ ... \\ ... \\ ... \}` 伪装成方程组（图：线性方程组矩阵
 *       表示渲染异常），但 `\\` 在普通 `$$...$$` 里没有"换行"语义；
 *       自动改写成 `\begin{cases}...\end{cases}`，恢复多行排版。
 *   (c) 不在任何 `\begin{...}...\end{...}` 环境内的孤立 `\\`（连续多行公式），
 *       自动包裹成 `\begin{aligned}...\end{aligned}`，避免 `\\` 被当作非法换行。
 *
 * 注意：只对块级公式（display 模式）调用，行内 `$...$` 不应包含换行/方程组。
 */
function sanitizeMathExpr(expr) {
  if (!expr) return expr;
  let s = String(expr);

  // (a) 把字面 `\n`（反斜杠 + 字母 n，且后边不再是字母——避免误伤 \nu \neq 等）
  //     替换成单个空格。同理覆盖 `\r`、`\t`、`\v`、`\f` 这些 JSON 转义残留物，
  //     它们在 LaTeX 里都不是合法命令。
  s = s.replace(/\\([nrtvf])(?![A-Za-z])/g, " ");

  // 检测公式是否已经显式声明了多行环境（cases / aligned / array / matrix 等）。
  // 已声明就不再做 (b)(c) 兜底，避免把合法环境包多一层。
  const hasEnv = /\\begin\{[^}]+\}/.test(s);

  if (!hasEnv) {
    // (b) 单大括号 + \\ 行分隔的"伪方程组"：`\{ ... \\ ... \\ ... \}`
    //     用 [\s\S]+? 非贪婪匹配整段（含双反斜杠），整体替换为 cases 环境。
    s = s.replace(/\\\{\s*([\s\S]+?)\s*\\\}/g, (whole, inner) => {
      // 仅当内部确实包含至少一处 `\\` 行分隔（LaTeX 行终止）才转 cases。
      // 匹配 `\\` 字面：在原字符串里是 `\\\\`（两个反斜杠对）。
      if (/\\\\/.test(inner)) {
        return "\\begin{cases}" + inner + "\\end{cases}";
      }
      return whole;
    });

    // (c) 仍未启用环境、但存在裸 `\\` 行分隔：用 aligned 兜底
    if (!/\\begin\{[^}]+\}/.test(s) && /\\\\/.test(s)) {
      s = "\\begin{aligned}" + s + "\\end{aligned}";
    }
  }

  return s;
}

/**
 * 将 LaTeX 公式渲染为 KaTeX HTML，再交给 marked 处理 markdown。
 * 支持的公式语法：
 *   行内：$...$  或  \(...\)
 *   块级：$$...$$  或  \[...\]
 *
 * 此外会先调用 autoWrapBareLatex 给"裸 LaTeX"补上 $...$，
 * 兼容 LLM 偶尔忘记加 $ 的情况。
 */
export function renderLatex(text) {
  if (!text) return "";

  // 0. 先把裸 LaTeX 自动包裹 $...$
  text = autoWrapBareLatex(text);

  // 占位符映射，避免 marked 破坏 KaTeX 输出的 HTML
  // 使用 marked 不会做特殊处理的纯字母数字串作为占位符；
  // 之前用的 %%KATEX_n%% 在 marked 自动链接 / URL 检测时偶发被吞或截断。
  const placeholders = [];
  function hold(html) {
    const id = `xxKATEXPLACEHOLDER${placeholders.length}xxKATEXEND`;
    placeholders.push(html);
    return id;
  }

  // 1. 块级公式：$$...$$ （可跨行）
  let result = text.replace(/\$\$(\s*[\s\S]+?\s*)\$\$/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(sanitizeMathExpr(expr.trim()), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 2. 块级公式：\[...\] （可跨行）
  result = result.replace(/\\\[([\s\S]+?)\\\]/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(sanitizeMathExpr(expr.trim()), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 3. 行内公式：\(...\)
  result = result.replace(/\\\((.+?)\\\)/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: false,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 4. 行内公式：$...$ （不匹配 $$，不跨行）
  result = result.replace(
    /(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)/g,
    (_, expr) => {
      try {
        return hold(
          katex.renderToString(expr.trim(), {
            displayMode: false,
            throwOnError: false,
          }),
        );
      } catch {
        return _;
      }
    },
  );

  // 5. 还原占位符
  for (let i = 0; i < placeholders.length; i++) {
    result = result.replace(
      `xxKATEXPLACEHOLDER${i}xxKATEXEND`,
      () => placeholders[i],
    );
  }

  return result;
}

// 将 markdown + LaTeX 转为安全 HTML
export function renderMd(text) {
  if (!text) return "";
  // 先处理 LaTeX 公式，再渲染 markdown
  const withLatex = renderLatex(text);
  // DOMPurify 需要放行 KaTeX 的 HTML 标签和属性
  return DOMPurify.sanitize(marked.parse(withLatex), {
    ADD_TAGS: [
      "span",
      "math",
      "semantics",
      "mrow",
      "mi",
      "mo",
      "mn",
      "msup",
      "msub",
      "mfrac",
      "mtext",
      "annotation",
      "mover",
      "munder",
      "mtable",
      "mtr",
      "mtd",
      "mspace",
      "msqrt",
      "mroot",
      "menclose",
    ],
    ADD_ATTR: [
      "class",
      "style",
      "mathvariant",
      "encoding",
      "displaystyle",
      "scriptlevel",
      "xmlns",
      "aria-hidden",
      "role",
    ],
  });
}
