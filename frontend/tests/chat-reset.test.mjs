import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import { setImmediate } from "node:timers";
import { URL } from "node:url";
import { parse as parseVue } from "@vue/compiler-sfc";
import { parse } from "@babel/parser";

const source = readFileSync(
  new URL("../src/views/ChatView.vue", import.meta.url),
  "utf8",
);
const script = parseVue(source).descriptor.scriptSetup.content;
const names = [
  "resetToIdle",
  "sendMessage",
  "sendWithSSE",
  "sendLocal",
  "classifyError",
];
const functions = parse(script, { sourceType: "module" })
  .program.body.filter(
    (n) => n.type === "FunctionDeclaration" && names.includes(n.id.name),
  )
  .map((n) => script.slice(n.start, n.end))
  .join("\n");
const flush = () => new Promise((resolve) => setImmediate(resolve));

function harness() {
  const streams = [];
  const context = {
    console: { warn() {} },
    Date,
    Math,
    Map,
    Object,
    window: {},
    sessionStartTime: null,
    sseController: null,
    pendingCardSlots: new Map(),
    nextTick: async () => {},
    scrollBottom() {},
    now: () => "12:00",
    renderMd: (text) => text,
    sessionApi: {
      recordDuration: async () => {},
      streamMessage(sessionId, text, callbacks) {
        const controller = new globalThis.AbortController();
        const listeners = new Set();
        const add = controller.signal.addEventListener.bind(controller.signal);
        const remove = controller.signal.removeEventListener.bind(
          controller.signal,
        );
        controller.signal.addEventListener = (type, listener, options) => {
          if (type === "abort") listeners.add(listener);
          return add(type, listener, options);
        };
        controller.signal.removeEventListener = (type, listener, options) => {
          if (type === "abort") listeners.delete(listener);
          return remove(type, listener, options);
        };
        streams.push({ sessionId, text, callbacks, controller, listeners });
        return controller;
      },
    },
  };
  const state = {
    currentSessionId: "first-session",
    phase: "learning",
    isGenerating: false,
    isThinking: false,
    inputText: "",
    inputBox: null,
    messages: [],
    slides: [],
    cards: [],
    currentCardIndex: 0,
    currentIndex: 0,
    topicInput: "",
    genProgress: 0,
    genStage: -1,
  };
  for (const [name, value] of Object.entries(state)) context[name] = { value };
  vm.createContext(context);
  vm.runInContext(functions, context);
  return { context, streams };
}

for (const partial of [false, true]) {
  test(`reset settles an aborted response ${partial ? "after partial text" : "before its first event"}`, async () => {
    const { context: c, streams } = harness();
    let settled = false;
    const sending = c.sendMessage("First question").then(() => {
      settled = true;
    });
    await flush();
    assert.equal(streams.length, 1);
    assert.equal(c.isGenerating.value, true);
    if (partial) streams[0].callbacks.onTextChunk("Partial answer", 1);

    c.resetToIdle();
    await flush();

    assert.equal(streams[0].controller.signal.aborted, true);
    assert.equal(settled, true);
    assert.equal(c.isGenerating.value, false);
    assert.equal(c.isThinking.value, false);
    assert.equal(c.phase.value, "idle");
    assert.equal(c.messages.value.length, 0);
    assert.equal(streams[0].listeners.size, 0);
    await sending;
  });
}

test("an immediate new session starts a stream and ignores the canceled stream", async () => {
  const { context: c, streams } = harness();
  const first = c.sendMessage("First question");
  await flush();
  c.resetToIdle();
  c.currentSessionId.value = "second-session";
  c.phase.value = "learning";
  // Start before the canceled sendMessage continuation gets a chance to run.
  const second = c.sendMessage("Second question");
  await flush();

  assert.equal(streams.length, 2);
  assert.equal(streams[1].sessionId, "second-session");
  assert.equal(c.isGenerating.value, true);
  streams[1].callbacks.onTextChunk("Current answer", 1);
  const currentMessages = JSON.stringify(c.messages.value);

  streams[0].callbacks.onTextChunk("Late old text", 1);
  streams[0].callbacks.onDone();
  await streams[0].callbacks.onError(new Error("Late old error"));
  await flush();

  assert.equal(JSON.stringify(c.messages.value), currentMessages);
  assert.equal(c.isGenerating.value, true);
  assert.equal(c.sseController, streams[1].controller);
  streams[1].callbacks.onDone();
  await second;
  await first;
  assert.equal(c.isGenerating.value, false);
  assert.equal(c.messages.value[1].content, "Current answer");
  assert.equal(streams[1].listeners.size, 0);
});

test("normal completion preserves the answer and releases the abort listener", async () => {
  const { context: c, streams } = harness();
  const sending = c.sendMessage("Question");
  await flush();
  streams[0].callbacks.onTextChunk("Answer", 1);
  streams[0].callbacks.onDone();
  await sending;
  assert.equal(c.messages.value[1].content, "Answer");
  assert.equal(c.isGenerating.value, false);
  assert.equal(c.isThinking.value, false);
  assert.equal(streams[0].controller.signal.aborted, false);
  assert.equal(streams[0].listeners.size, 0);
});

test("a stream error still displays a message and releases the abort listener", async () => {
  const { context: c, streams } = harness();
  const sending = c.sendMessage("Question");
  await flush();
  await streams[0].callbacks.onError(new Error("Synthetic failure"));
  await sending;
  assert.match(c.messages.value[1].content, /Synthetic failure/);
  assert.equal(c.isGenerating.value, false);
  assert.equal(c.isThinking.value, false);
  assert.equal(streams[0].listeners.size, 0);
});
