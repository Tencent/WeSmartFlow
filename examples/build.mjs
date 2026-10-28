import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import {
  examplesDir,
  getBuildableTopics,
  loadCatalog,
  resolveChildPath,
} from "./catalog.mjs";

const projectDir = resolve(examplesDir, "..");
const publicDir = resolve(projectDir, "frontend/public");
const stagingRoot = resolveChildPath(publicDir, ".examples-staging", "stagingRoot");
const onlyIndex = process.argv.indexOf("--only");
const onlyId = onlyIndex >= 0 ? process.argv[onlyIndex + 1] : null;

function fail(message) {
  console.error(`[explore] ${message}`);
  process.exit(1);
}

function readPackage(packagePath, topicId) {
  try {
    return JSON.parse(readFileSync(packagePath, "utf8"));
  } catch (error) {
    fail(`${topicId} 的 package.json 无法读取：${error.message}`);
  }
}

if (onlyIndex >= 0 && !onlyId) fail("--only 后必须提供主题 id");

let catalog;
try {
  catalog = loadCatalog();
} catch (error) {
  fail(error.message);
}

const buildableTopics = getBuildableTopics(catalog);
if (onlyId && !buildableTopics.some((topic) => topic.id === onlyId)) {
  fail(`没有找到可构建的主题：${onlyId}`);
}

// 所有主题先构建到临时目录；失败时保留上一份可用产物。
rmSync(stagingRoot, { recursive: true, force: true });

// npm.cmd 不能直接由 spawnSync 执行；复用当前 npm 的 JavaScript 入口。
const npmCli = process.env.npm_execpath;
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
for (const topic of buildableTopics) {
  if (onlyId && topic.id !== onlyId) continue;

  let packageDir;
  let outputDir;
  let stagingDir;
  try {
    packageDir = resolveChildPath(examplesDir, topic.build.packageDir, `${topic.id}.build.packageDir`);
    outputDir = resolveChildPath(publicDir, topic.build.outputDir, `${topic.id}.build.outputDir`);
    stagingDir = resolveChildPath(stagingRoot, topic.id, `${topic.id}.stagingDir`);
  } catch (error) {
    fail(error.message);
  }

  const packagePath = resolve(packageDir, "package.json");
  if (!existsSync(packagePath)) fail(`${topic.id} 的目录中没有 package.json：${packageDir}`);
  const packageJson = readPackage(packagePath, topic.id);
  if (!packageJson.scripts?.[topic.build.script]) {
    fail(`${topic.id} 缺少 npm script：${topic.build.script}`);
  }

  const publicPath = `/${topic.build.outputDir.replace(/^\/+|\/+$/g, "")}/`;
  console.log(`[explore] 构建 ${topic.title} -> ${publicPath}`);

  const npmArgs = [...(npmCli ? [npmCli] : []), "run", topic.build.script];
  const result = spawnSync(npmCli ? process.execPath : npmCommand, npmArgs, {
    cwd: packageDir,
    stdio: "inherit",
    env: {
      ...process.env,
      WESMARTFLOW_EXAMPLE_ID: topic.id,
      WESMARTFLOW_EXAMPLE_OUT_DIR: stagingDir,
      WESMARTFLOW_EXAMPLE_PUBLIC_PATH: publicPath,
    },
  });
  if (result.error) {
    rmSync(stagingDir, { recursive: true, force: true });
    fail(`${topic.title} 构建启动失败：${result.error.message}`);
  }
  if (result.status !== 0) {
    rmSync(stagingDir, { recursive: true, force: true });
    process.exit(result.status ?? 1);
  }

  let entryPath;
  try {
    entryPath = resolveChildPath(stagingDir, topic.build.entryFile, `${topic.id}.build.entryFile`);
  } catch (error) {
    rmSync(stagingDir, { recursive: true, force: true });
    fail(error.message);
  }
  if (!existsSync(entryPath) || !statSync(entryPath).isFile()) {
    rmSync(stagingDir, { recursive: true, force: true });
    fail(`${topic.title} 构建完成但缺少入口文件：${topic.build.entryFile}`);
  }

  // Cover every generated chapter page as well as the six example entrypoints.
  function injectAuth(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const file = resolve(dir, entry.name);
      if (entry.isDirectory()) injectAuth(file);
      else if (entry.name.endsWith(".html")) {
        const html = readFileSync(file, "utf8");
        if (!html.includes('src="/example-auth.js"')) {
          writeFileSync(file, html.replace(/<head([^>]*)>/i, '<head$1><script src="/example-auth.js"></script>'));
        }
      }
    }
  }
  injectAuth(stagingDir);
  mkdirSync(dirname(outputDir), { recursive: true });
  rmSync(outputDir, { recursive: true, force: true });
  renameSync(stagingDir, outputDir);
}

rmSync(stagingRoot, { recursive: true, force: true });
