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
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).focus(); [...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`,
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
    await mkdir(process.env.REASSIGN_QA ? "qa/34" : "qa/33", { recursive: true });
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    await writeFile(
      `${process.env.REASSIGN_QA ? "qa/34" : "qa/33"}/${width}-live.png`,
      Buffer.from(data, "base64"),
    );
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
  await writeFile(
    process.env.REASSIGN_QA
      ? "qa/34/390-live-contact-cleared.png"
      : "qa/33/390-live-contact-cleared.png",
    Buffer.from(data, "base64"),
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS live FastAPI/PostgreSQL: authenticated dashboard, four real reminder categories, 390/768/1440 layouts, contact saved, quarterly reminder absent from backend response and refreshed dashboard.",
  );
  if (process.env.REASSIGN_QA) {
    await mkdir("qa/34", { recursive: true });
    await evaluate("document.querySelector('a[href$=\"#relationship-owner\"]').click()");
    await until("document.activeElement.id==='relationship-owner'");
    await clickText("Reassign donor");
    await until("document.querySelector('dialog[open] select option[value=\"1\"]')");
    const choose = () =>
      evaluate(
        "(() => { const s=document.querySelector('dialog[open] select'); s.value='1'; s.dispatchEvent(new Event('change',{bubbles:true})); })()",
      );
    await choose();
    await evaluate("document.querySelector('dialog[open] textarea').focus()");
    await call("Input.insertText", { text: "Synthetic handoff for student outreach" });
    assert.equal(await evaluate("document.querySelector('dialog[open] textarea').maxLength"), 2000);
    assert.equal(
      await evaluate("document.querySelector('dialog[open] button.button').disabled"),
      true,
    );
    await evaluate("document.querySelector('dialog[open] input[type=checkbox]').click()");
    for (const [width, height] of [
      [1440, 900],
      [768, 1024],
      [390, 844],
      [720, 450],
    ]) {
      await call("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile: false,
      });
      assert.equal(await evaluate("document.documentElement.scrollWidth<=innerWidth"), true);
      await delay(300);
      const { data } = await call("Page.captureScreenshot", { format: "png" });
      await writeFile(`qa/34/${width}-dialog.png`, Buffer.from(data, "base64"));
    }
    // Keyboard trap and Escape restore the opener without a write.
    await evaluate("[...document.querySelectorAll('dialog[open] button')].at(-1).focus()");
    await key("Tab", "Tab", 9);
    assert.equal(
      await evaluate("document.activeElement.getAttribute('aria-label')"),
      "Close sheet",
    );
    await key("Escape", "Escape", 27);
    assert.equal(await evaluate("document.activeElement.textContent.trim()"), "Reassign donor");
    await clickText("Reassign donor");
    await until("document.querySelector('dialog[open] select')");
    await choose();
    await evaluate("document.querySelector('dialog[open] textarea').focus()");
    await call("Input.insertText", { text: "Synthetic handoff for student outreach" });
    // Controlled transport failures exercise recovery; success below uses the real API.
    let failure = 409;
    const handler = socket.onmessage;
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.method === "Fetch.requestPaused")
        void call("Fetch.fulfillRequest", {
          requestId: message.params.requestId,
          responseCode: failure,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }],
          body: Buffer.from(
            JSON.stringify({ error: { message: "Synthetic conflict or permission change" } }),
          ).toString("base64"),
        });
      handler(event);
    };
    await call("Fetch.enable", {
      patterns: [{ urlPattern: "*/reassign", requestStage: "Request" }],
    });
    for (const status of [409, 500, 422, 501, 401, 403]) {
      failure = status;
      await evaluate("document.querySelector('dialog[open] input[type=checkbox]').click()");
      await clickText("Confirm reassignment");
      await until(
        "document.querySelector('dialog[open] [role=alert]') && !document.querySelector('dialog[open] input[type=checkbox]').checked",
      );
      assert.equal(
        await evaluate("document.querySelector('dialog[open] textarea').value"),
        "Synthetic handoff for student outreach",
      );
      if (status === 403)
        assert.equal(
          await evaluate("document.querySelector('dialog[open] button.button').disabled"),
          true,
        );
    }
    await call("Fetch.disable");
    await clickText("Cancel");
    await clickText("Reassign donor");
    await until("document.querySelector('dialog[open] select')");
    await choose();
    await evaluate("document.querySelector('dialog[open] textarea').focus()");
    await call("Input.insertText", { text: "Synthetic handoff for student outreach" });
    await evaluate("document.querySelector('dialog[open] input[type=checkbox]').click()");
    await clickText("Confirm reassignment");
    await until("!document.querySelector('dialog[open]')");
    const history = await evaluate("fetch('/api/app/donors/4/owner-history').then(r=>r.json())");
    assert.equal(history.items[0].to_user.id, 1);
    assert.equal(history.items[0].from_user.id, 2);
    assert.equal(history.items[0].method, "manual");
    assert.equal(history.items[0].changed_by.id, 1);
    assert.equal(history.items[0].reason, "Synthetic handoff for student outreach");
    await call("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await evaluate("document.querySelector('.owner-history').open=true");
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    await writeFile("qa/34/390-history.png", Buffer.from(data, "base64"));
    await evaluate("document.querySelector('a[href=\"/\"]').click()");
    await until("document.querySelectorAll('.todo-row').length===2");
    assert.equal(
      await evaluate("document.querySelectorAll('.reassignment-workspace .todo-row').length"),
      0,
    );
    assert.deepEqual(errors, []);
    console.log(
      "PASS #34: real dashboard handoff/history, six failure statuses, preserved reason, validation, focus trap/restoration, responsive screenshots, refreshed dashboard.",
    );
  }
} finally {
  socket?.close();
  browser.kill();
}
