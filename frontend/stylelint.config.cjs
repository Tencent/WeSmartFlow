module.exports = {
  extends: ["stylelint-config-standard"],
  plugins: ["@stylistic/stylelint-plugin"],
  rules: {
    "@stylistic/number-leading-zero": "never", // 0.5 -> .5
    "@stylistic/string-quotes": "single",
  },
};
