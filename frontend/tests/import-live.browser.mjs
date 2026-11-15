// Start Vite, then run: node tests/detail.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9343;
const profile = resolve(".test-build/import-live-browser");
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

  const shot = async (name) => {
    await mkdir("qa/22", { recursive: true });
    const result = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    await writeFile(`qa/22/${name}.png`, Buffer.from(result.data, "base64"));
  };
  const size = async (width, height = width === 390 ? 844 : width === 768 ? 1024 : 900) => {
    await call("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  };
  const widthOK = async () =>
    assert.equal(
      await evaluate("document.documentElement.scrollWidth <= innerWidth"),
      true,
      "No horizontal page overflow",
    );
  const chooseFile = async () => {
    await until("document.querySelector('input[type=file]')");
    await evaluate(
      `(() => { const input=document.querySelector('input[type=file]'); const data=new DataTransfer(); data.items.add(new File(['Name,Email\\nSynthetic,synthetic@example.test'], 'synthetic-import.csv', {type:'text/csv'})); input.files=data.files; input.dispatchEvent(new Event('change',{bubbles:true})); })()`,
    );
  };
  const select = async (selector, value) => {
    await evaluate(
      `(() => { const s=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(s),'value').set; setter.call(s,${JSON.stringify(value)}); s.dispatchEvent(new Event('change',{bubbles:true})); s.dispatchEvent(new Event('input',{bubbles:true})); })()`,
    );
  };
  const open = async (path = "/import") => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until("document.querySelector('h1')");
  };
  // This runner deliberately does not intercept any API requests.
  const credentials = JSON.parse(await readFile(".test-build/22-session.json", "utf8"));
  await size(1440);
  await open("/login");
  assert.equal(
    await evaluate(
      `fetch('/api/app/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(credentials)})}).then(r=>r.status)`,
    ),
    200,
  );
  const uploadCSV = async (source, content, name) => {
    await open();
    await until("document.querySelector('input[type=file]')");
    await select("select", source);
    await evaluate(
      `(() => { const input=document.querySelector('input[type=file]'); const data=new DataTransfer(); data.items.add(new File([${JSON.stringify(content)}],${JSON.stringify(name)},{type:'text/csv'})); input.files=data.files;input.dispatchEvent(new Event('change',{bubbles:true})); })()`,
    );
    await clickText("Preview file");
    await until("document.querySelector('.reconciliation-table')");
  };
  const commitImport = async () => {
    await clickText("Review & confirm");
    await until("document.querySelector('dialog[open]')");
    await clickText("Confirm import");
    await until("document.querySelector('.import-success')");
  };
  // Recover only unfinished records in this isolated synthetic QA database from an interrupted run.
  await open("/review");
  await until(
    "document.querySelector('.review-card') || document.body.textContent.includes('The review desk is clear')",
  );
  while (await evaluate("!!document.querySelector('.review-card')")) {
    await select(".review-decision select", "anonymous");
    await evaluate("document.querySelector('.review-decision button').click()");
    await clickText("Save decision");
    await until("!document.querySelector('dialog[open]')");
    await delay(250);
  }
  const run = Date.now();
  for (const width of [390, 768, 1440]) {
    await size(width);
    const tag = `${run}-${width}`;
    await uploadCSV(
      "spreadsheet",
      `Name,Email\nJordan QA ${tag},qa-${tag}@example.test\n`,
      `synthetic-seed-${tag}.csv`,
    );
    assert.equal(
      await evaluate("document.querySelectorAll('.import-metrics strong')[1].textContent"),
      "0",
    );
    await commitImport();
    await uploadCSV(
      "zeffy",
      `Payment ID,Date,Amount,First name,Last name,Email\nqa-${tag},2026-11-14,125.00,Alex,QA ${tag},qa-${tag}@example.test\nqa-invalid-${tag},31/31/2025,20.00,Synthetic,Invalid,invalid-${tag}@example.test\n`,
      `synthetic-zeffy-${tag}.csv`,
    );
    assert.ok(
      (await evaluate("document.querySelector('.invalid-rows').textContent")).includes(
        "File row 3",
      ),
    );
    await widthOK();
    await evaluate("document.querySelector('.import-file-heading').scrollIntoView()");
    await shot(`${width}-live-preview`);
    await commitImport();
    await shot(`${width}-live-success`);
    await open("/review");
    await until("document.querySelector('.review-card')");
    await widthOK();
    await evaluate("document.querySelector('.review-card').scrollIntoView()");
    await shot(`${width}-live-comparison`);
    await evaluate(
      "document.querySelector('.identity-comparison > section + section').scrollIntoView()",
    );
    await shot(`${width}-live-candidates`);
    await evaluate("document.querySelector('.review-decision').scrollIntoView({block:'center'})");
    await shot(`${width}-live-decision`);
    const value = await evaluate(
      "document.querySelector('.review-decision select option:nth-child(2)').value",
    );
    assert.ok(value.startsWith("link:"));
    await select(".review-decision select", value);
    await evaluate("document.querySelector('.review-decision button').click()");
    await clickText("Save decision");
    await until("!document.querySelector('dialog[open]')");
    await until("document.body.textContent.includes('The review desk is clear')");
    // One physical source row generates two gifts; a second anonymous row stays protected.
    await uploadCSV(
      "benevity",
      `Transaction ID,Donation Date,Donation Amount,Match Amount,Donation Currency,Donor First Name,Donor Last Name,Donor Email\nben-${tag},2026-11-14,100.00,50.00,USD,,,\nben-anon-${tag},2026-11-14,25.00,0,USD,,,\n`,
      `synthetic-benevity-${tag}.csv`,
    );
    assert.deepEqual(
      await evaluate(
        "[...document.querySelectorAll('.import-metrics strong')].slice(0,2).map(n=>n.textContent)",
      ),
      ["2", "3"],
    );
    await commitImport();
    await open("/review");
    await clickText("Unattributed gifts");
    await until("document.querySelector('.gift-review')");
    assert.equal(
      await evaluate(
        "[...document.querySelectorAll('.gift-review')].filter(n=>n.textContent.includes('benevity')&&n.textContent.includes('anonymous')).every(n=>!n.querySelector('button,input,select'))",
      ),
      true,
    );
  }
  assert.deepEqual(errors, []);
  console.log(
    "PASS: live FastAPI + isolated local PostgreSQL: donor-only import, invalid source row, duplicate identity link, confirmation + commit, Benevity row/gift accounting and anonymous attribution protection at 390, 768 and 1440. No API mocks.",
  );
} finally {
  socket?.close();
  browser.kill();
}
