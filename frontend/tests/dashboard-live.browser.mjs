// Start Vite, then run: npm run test:dashboard:live
// Real API requests to an isolated local database with synthetic records. Start dashboard-local.py first.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9349;
const profile = resolve(".test-build/dashboard-live-browser");
await mkdir(profile, { recursive: true });
const browser = spawn(
  process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe",
  [
    "--headless",
    "--disable-gpu",
    "--no-first-run",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { windowsHide: true, stdio: "ignore" },
);
let socket;
try {
  let target;
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      target = await (
        await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })
      ).json();
      break;
    } catch {
      await delay(100);
    }
  }
  assert.ok(target, "Headless Chrome starts");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok, fail) => {
    socket.onopen = ok;
    socket.onerror = fail;
  });
  let nextId = 0;
  const pending = new Map();
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (pending.has(message.id)) {
      const { ok, fail, timer } = pending.get(message.id);
      clearTimeout(timer);
      pending.delete(message.id);
      if (message.error) fail(new Error(JSON.stringify(message.error)));
      else ok(message.result);
    }
  };
  const call = (method, params = {}) =>
    new Promise((ok, fail) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        pending.delete(id);
        fail(new Error(`Timeout: ${method}`));
      }, 15000);
      pending.set(id, { ok, fail, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) => {
    const result = await call("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const until = async (expression) => {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate(`Boolean(${expression})`)) return;
      await delay(100);
    }
    assert.fail(`Timed out: ${expression}`);
  };
  const key = async (key, code, windowsVirtualKeyCode) => {
    await call("Input.dispatchKeyEvent", {
      type: "keyDown",
      key,
      code,
      windowsVirtualKeyCode,
      text: key === "Enter" ? "\r" : key.length === 1 ? key : undefined,
    });
    await call("Input.dispatchKeyEvent", { type: "keyUp", key, code, windowsVirtualKeyCode });
  };
  const clickText = (text) =>
    evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`,
    );
  const errors = [];
  const oldHandler = socket.onmessage;
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown")
      errors.push(message.params.exceptionDetails.text);
    oldHandler(event);
  };
  await call("Runtime.enable");
  await call("Page.enable");

  // No request interception: Vite proxies every call to the isolated local backend.
  const credentials = JSON.parse(await readFile(".test-build/33-session.json", "utf8"));
  await call("Page.navigate", { url: "http://127.0.0.1:5173/login" });
  await until("document.querySelector('h1')");
  assert.equal(
    await evaluate(
      `fetch('/api/app/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(credentials)})}).then(r=>r.status)`,
    ),
    200,
  );
  await call("Page.navigate", { url: "http://127.0.0.1:5173/" });
  await until("document.querySelectorAll('.todo-row').length===4");
  const before = await evaluate("fetch('/api/app/reminders?scope=mine').then(r=>r.json())");
  assert.deepEqual(before.items.map((r) => r.type).sort(), [
    "needs_reassignment",
    "next_step_due",
    "quarterly_due",
    "thank_you_due",
  ]);
  for (const [width, height] of [
    [1440, 900],
    [768, 1024],
    [390, 844],
  ]) {
    await call("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    assert.equal(await evaluate("document.documentElement.scrollWidth<=innerWidth"), true);
    await mkdir("qa/33", { recursive: true });
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    await writeFile(`qa/33/${width}-live.png`, Buffer.from(data, "base64"));
  }
  await evaluate("document.querySelector('a[href$=\"#log-contact\"]').click()");
  await until("document.activeElement.id==='log-contact'");
  await clickText("Log contact");
  await evaluate("document.querySelector('input[value=call]').click()");
  await clickText("Save contact");
  await until(
    "!document.querySelector('dialog[open]') && document.querySelector('.save-notice').textContent.includes('Contact logged')",
  );
  const after = await evaluate("fetch('/api/app/reminders?scope=mine').then(r=>r.json())");
  assert.equal(
    after.items.some((r) => r.type === "quarterly_due"),
    false,
  );
  assert.equal(after.items.length, 3);
  await evaluate("document.querySelector('a[href=\"/\"]').click()");
  await until("document.querySelectorAll('.todo-row').length===3");
  assert.equal(
    await evaluate(
      "document.querySelector('.todo-workspace').textContent.includes('Synthetic Alex Rivera')",
    ),
    false,
  );
  const { data } = await call("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  await writeFile("qa/33/390-live-contact-cleared.png", Buffer.from(data, "base64"));
  assert.deepEqual(errors, []);
  console.log(
    "PASS live FastAPI/PostgreSQL: authenticated dashboard, four real reminder categories, 390/768/1440 layouts, contact saved, quarterly reminder absent from backend response and refreshed dashboard.",
  );
} finally {
  socket?.close();
  browser.kill();
}
