import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import globals from "globals";
import vueParser from "vue-eslint-parser";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default [
  { ignores: ["dist/**", "node_modules/**", "coverage/**"] },

  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  ...tseslint.configs.recommended,

  {
    files: ["**/*.{js,jsx,ts,tsx,vue}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },

  // 关键：让 .vue 用 vue-eslint-parser；script 里再用 TS parser（如果你有 TS）
  {
    files: ["**/*.vue"],
    rules: { "vue/no-v-html": "off" },
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser, // 如果你完全没用 TS，可改成 espree 或直接删掉这一行
        extraFileExtensions: [".vue"],
      },
    },
  },
  prettier,
];
