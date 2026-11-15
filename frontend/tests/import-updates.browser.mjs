// Run with Vite on localhost:5173. Uses a local headless Chromium and mocked APIs.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const binary = process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const profile = resolve(".test-build/browser-profile");
await mkdir(profile, { recursive: true });
const browser = spawn(
  binary,
  [
    "--headless",
    "--disable-gpu",
    "--no-first-run",
    "--remote-debugging-port=9327",
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
        await fetch("http://127.0.0.1:9327/json/new?about:blank", { method: "PUT" })
      ).json();
      break;
    } catch {
      await delay(100);
    }
  }
  assert.ok(target, "Headless browser must start");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok, fail) => {
    socket.onopen = ok;
    socket.onerror = fail;
  });
  let next = 0;
  const pending = new Map();
  socket.onclose = ({ code, reason }) => {
    for (const { fail } of pending.values()) fail(new Error(`CDP closed: ${code} ${reason}`));
  };
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (pending.has(message.id)) {
      const { ok, fail } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) fail(new Error(JSON.stringify(message.error)));
      else ok(message.result);
    }
  };
  const call = (method, params = {}) =>
    new Promise((ok, fail) => {
      const id = ++next;
      const timer = setTimeout(() => fail(new Error(`CDP timeout: ${method}`)), 10000);
      pending.set(id, {
        ok: (result) => {
          clearTimeout(timer);
          ok(result);
        },
        fail: (error) => {
          clearTimeout(timer);
          fail(error);
        },
      });
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
      if (await evaluate(expression)) return;
      await delay(100);
    }
    assert.fail(`Timed out: ${expression}`);
  };
  await call("Page.enable");
  await call("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await call("Page.addScriptToEvaluateOnNewDocument", {
    source: `
    const empty = {count:0,cents:0,gift_count:0,donation_cents:0,match_cents:0};
    const summary = {rows_read:1,gift_count:0,total_cents:0,donation_cents:0,match_cents:0,
      new_gifts:empty,already_imported:empty,needs_review:empty,invalid:empty,anonymous:empty,
      donor_updates:{...empty,count:1},updated_count:1,new_donors:0,donors_matched:1,
      unmapped_campaigns:[],rows_reconcile:true,cents_reconcile:true,reconciles:true};
    const batch = {id:12,source:'spreadsheet',filename:'updates.csv',status:'previewed',summary};
    const preview = {batch,summary,commit_allowed:true,invalid_rows:[],updates:[{
      donor_id:7,donor_name:'Ada Jones',changes:{
        email:{new_value:'new@example.org',old_hidden:true},
        notes:{new_value:'New note',old_hidden:true}
      }}]};
    window.commits = [];
    window.fetch = async (url, options = {}) => {
      if (url === '/api/app/auth/me') return Response.json({id:2,email:'sam@example.org',
        display_name:'Sam',is_super_admin:false,governance:{mode:'flat',reassign_scope:'anyone'}});
      if (url === '/api/app/imports/preview') return Response.json(preview);
      if (url === '/api/app/imports/12/commit') {
        window.commits.push(JSON.parse(options.body));
        return Response.json({...batch,status:'committed',summary:{...summary,
          updated_count:JSON.parse(options.body).approved_updates.length}});
      }
      throw new Error('Unexpected fetch: ' + url);
    };
  `,
  });
  await call("Page.navigate", { url: "http://127.0.0.1:5173/import" });
  await until("Boolean(document.querySelector('input[type=file]'))");
  const upload = async () => {
    await evaluate(`(() => {
      const input = document.querySelector('input[type=file]');
      const data = new DataTransfer();
      data.items.add(new File(['Name,Email\\nAda Jones,new@example.org\\n'], 'updates.csv', {type:'text/csv'}));
      input.files = data.files; input.dispatchEvent(new Event('change', {bubbles:true}));
    })()`);
    await until("!document.querySelector('form button').disabled");
    await evaluate("document.querySelector('form button').click()");
    await until(
      "[...document.querySelectorAll('button')].some(b=>b.textContent==='Review donor updates')",
    );
    await evaluate(
      "[...document.querySelectorAll('button')].find(b=>b.textContent==='Review donor updates').click()",
    );
    await until("Boolean(document.querySelector('dialog[open]'))");
    assert.equal(await evaluate("document.querySelectorAll('dialog input:checked').length"), 0);
    assert.equal(
      await evaluate("document.activeElement.type"),
      "checkbox",
      "Modal focuses first checkbox",
    );
    assert.equal(await evaluate("document.documentElement.scrollWidth <= innerWidth"), true);
  };
  await upload();
  await evaluate(
    "[...document.querySelectorAll('dialog button')].find(b=>b.textContent==='Commit import').click()",
  );
  await until("window.commits.length === 1");
  assert.deepEqual(await evaluate("window.commits[0]"), { approved_updates: [] });
  await upload();
  await call("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: " ",
    code: "Space",
    windowsVirtualKeyCode: 32,
  });
  await call("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: " ",
    code: "Space",
    windowsVirtualKeyCode: 32,
  });
  assert.equal(await evaluate("document.querySelectorAll('dialog input:checked').length"), 1);
  await mkdir("../docs/screenshots", { recursive: true });
  const screenshot = await call("Page.captureScreenshot", { format: "png" });
  await writeFile(
    "../docs/screenshots/105-donor-updates.png",
    Buffer.from(screenshot.data, "base64"),
  );
  await evaluate(
    "[...document.querySelectorAll('dialog button')].find(b=>b.textContent==='Commit import').click()",
  );
  await until("window.commits.length === 2");
  assert.deepEqual(await evaluate("window.commits[1]"), {
    approved_updates: [{ donor_id: 7, fields: ["email"] }],
  });
  await until("Boolean(document.querySelector('[role=status]'))");
  console.log(
    "PASS: unchecked defaults, keyboard selection, modal focus, mobile width, and exact commit payloads",
  );
} finally {
  socket?.close();
  browser.kill();
}
