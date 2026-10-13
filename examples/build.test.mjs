import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const sourceDir = path.dirname(fileURLToPath(import.meta.url));

function fixture(t, mode = "success") {
  const root = mkdtempSync(path.join(tmpdir(), "example build "));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const examples = path.join(root, "examples");
  const packageDir = path.join(examples, "Topic With Spaces");
  const outputDir = path.join(root, "frontend/public/demo");
  const npmCli = path.join(root, "runner with spaces/npm-cli.cjs");
  for (const dir of [packageDir, outputDir, path.dirname(npmCli)]) {
    mkdirSync(dir, { recursive: true });
  }
  for (const name of ["build.mjs", "catalog.mjs"]) {
    copyFileSync(path.join(sourceDir, name), path.join(examples, name));
  }
  const catalog = JSON.parse(
    readFileSync(path.join(sourceDir, "explore-catalog.json"), "utf8"),
  );
  const topic = catalog.topics[0];
  topic.id = "demo";
  topic.href = "/demo/index.html";
  topic.build = {
    runner: "npm",
    script: "build:wesmartflow",
    packageDir: "Topic With Spaces",
    outputDir: "demo",
    entryFile: "index.html",
  };
  catalog.topics = [topic];
  writeFileSync(
    path.join(examples, "explore-catalog.json"),
    JSON.stringify(catalog),
  );
  writeFileSync(
    path.join(packageDir, "package.json"),
    JSON.stringify({ scripts: { "build:wesmartflow": "unused by fixture" } }),
  );
  writeFileSync(path.join(outputDir, "previous.txt"), "previous build");
  writeFileSync(
    npmCli,
    `const fs = require("node:fs");
const path = require("node:path");
if (process.env.FIXTURE_MODE === "failure") process.exit(23);
const out = process.env.WESMARTFLOW_EXAMPLE_OUT_DIR;
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, "invocation.json"), JSON.stringify({
  args: process.argv.slice(2), cwd: process.cwd(),
  id: process.env.WESMARTFLOW_EXAMPLE_ID,
  publicPath: process.env.WESMARTFLOW_EXAMPLE_PUBLIC_PATH,
}));
if (process.env.FIXTURE_MODE !== "missing-entry") {
  fs.writeFileSync(path.join(out, "index.html"), "<html><head></head><body>demo</body></html>");
}
`,
  );
  const run = () =>
    spawnSync(process.execPath, [path.join(examples, "build.mjs")], {
      cwd: root,
      encoding: "utf8",
      env: { ...process.env, npm_execpath: npmCli, FIXTURE_MODE: mode },
    });
  return { run, packageDir, outputDir };
}

test("uses the current npm CLI with separate arguments and the build environment", (t) => {
  const { run, packageDir, outputDir } = fixture(t);
  const result = run();
  assert.equal(result.status, 0, result.stderr);
  const invocation = JSON.parse(
    readFileSync(path.join(outputDir, "invocation.json"), "utf8"),
  );
  assert.deepEqual(invocation, {
    args: ["run", "build:wesmartflow"],
    cwd: packageDir,
    id: "demo",
    publicPath: "/demo/",
  });
  assert.match(
    readFileSync(path.join(outputDir, "index.html"), "utf8"),
    /<script src="\/example-auth\.js"><\/script>/,
  );
  assert.equal(existsSync(path.join(outputDir, "previous.txt")), false);
});

test("preserves the child exit status and the previous successful output", (t) => {
  const { run, outputDir } = fixture(t, "failure");
  const result = run();
  assert.equal(result.status, 23, result.stderr);
  assert.equal(
    readFileSync(path.join(outputDir, "previous.txt"), "utf8"),
    "previous build",
  );
});

test("still rejects a successful child that does not produce an entry file", (t) => {
  const { run, outputDir } = fixture(t, "missing-entry");
  const result = run();
  assert.equal(result.status, 1);
  assert.match(result.stderr, /缺少入口文件/);
  assert.equal(
    readFileSync(path.join(outputDir, "previous.txt"), "utf8"),
    "previous build",
  );
});
