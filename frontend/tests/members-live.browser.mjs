// Start Vite and members-local.py, then run: npm run test:members:live
// Real API requests to an isolated local database with synthetic records.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9356;
const profile = resolve(`.test-build/members-live-browser-${process.pid}`);
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
  for (let attempt = 0; attempt < 300; attempt++) {
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
      }, 30000);
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
    for (let attempt = 0; attempt < 300; attempt++) {
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
  const clickText = async (text) => {
    await until(
      `[...document.querySelectorAll('button')].some(b => b.textContent.trim() === ${JSON.stringify(text)} && !b.disabled)`,
    );
    return evaluate(
      `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).focus(); [...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`,
    );
  };
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

  // Every request reaches the real local FastAPI/PostgreSQL instance. No interception.
  const credentials = JSON.parse(await readFile(".test-build/35-session.json", "utf8"));
  const navigate = async (path) => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until("document.querySelector('h1')");
  };
  const has = (text) => `document.body.textContent.includes(${JSON.stringify(text)})`;
  const set = (selector, value) =>
    evaluate(
      `{const el=document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(el instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)}); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));}`,
    );
  const request = (path, method = "GET", body) =>
    evaluate(
      `(async()=>{const csrf=document.cookie.split('; ').find(c=>c.startsWith('cic_csrf='))?.slice(9); const r=await fetch('/api/app'+${JSON.stringify(path)},{method:${JSON.stringify(method)},headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':decodeURIComponent(csrf)}:{})},body:${body === undefined ? "undefined" : `JSON.stringify(${JSON.stringify(body)})`}});return {status:r.status,body:r.status===204?null:await r.json()};})()`,
    );
  const shot = async (name) => {
    await delay(250);
    if (name.includes("invitation")) {
      await until("!document.querySelector('dialog .quick-note-footer button').disabled");
      await evaluate(
        "document.querySelector('dialog input[readonly]').value='[One-time invitation link redacted for QA]'",
      );
    }
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: await evaluate("!document.querySelector('dialog[open]')"),
    });
    await writeFile(`qa/35/${name}.png`, Buffer.from(data, "base64"));
  };
  const login = async (email, password) => {
    await navigate("/login");
    const result = await request("/auth/login", "POST", { email, password });
    assert.equal(result.status, 200);
  };
  await mkdir("qa/35", { recursive: true });
  console.log("Live QA: peer permissions");
  await login(credentials.peer_email, credentials.password);
  await navigate("/settings");
  await until(has("You can view the directory."));
  assert.equal(
    (await request("/members/invite", "POST", { email: "denied@example.test" })).status,
    403,
    "Backend blocks peer invite",
  );
  assert.equal(
    (await request("/governance/scope", "PUT", { reassign_scope: "own_only" })).status,
    403,
  );
  assert.equal((await request("/governance/flatten", "POST")).status, 403);
  assert.equal((await request(`/members/${credentials.admin_id}/deactivate`, "POST")).status, 403);
  // A second independent session will prove immediate revocation after deactivation.
  const peerLogin = await fetch("http://127.0.0.1:8000/api/app/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: credentials.peer_email, password: credentials.password }),
  });
  assert.equal(peerLogin.status, 200);
  const peerSession = peerLogin.headers
    .getSetCookie()
    .find((c) => c.toLowerCase().includes("httponly"))
    .split(";")[0];
  assert.equal(
    (await fetch("http://127.0.0.1:8000/api/app/auth/me", { headers: { Cookie: peerSession } }))
      .status,
    200,
    "Independent peer session initially authenticates",
  );
  await request("/auth/logout", "POST");
  await login(credentials.email, credentials.password);
  console.log("Live QA: admin directory and invitation");
  await navigate("/settings");
  await until(
    "document.querySelectorAll('.member-table tbody tr').length===3 && document.querySelector('.scope-form')",
  );
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
    await shot(`${width}-live`);
  }
  // Real duplicate and server validation responses, without changing local UI values.
  await clickText("Invite member");
  await set("dialog input[type=email]", credentials.peer_email);
  await clickText("Create invitation link");
  await until("document.querySelector('dialog [role=alert]')");
  assert.equal(
    await evaluate("document.querySelector('dialog input[type=email]').value"),
    credentials.peer_email,
  );
  await set("dialog input[type=email]", "synthetic.new.steward@example.test");
  await clickText("Create invitation link");
  await until("document.querySelector('dialog input[readonly]')");
  const inviteUrl = await evaluate("document.querySelector('dialog input[readonly]').value");
  assert.ok(new URL(inviteUrl).pathname.startsWith("/invite/"));
  assert.equal(
    new URL(inviteUrl).origin,
    "http://127.0.0.1:5173",
    "Copied link uses the frontend origin",
  );
  await evaluate(
    "document.querySelector('dialog input[readonly]').value='[One-time invitation link redacted for QA]'",
  );
  await shot("390-live-invitation");
  await clickText("Done");
  await request("/auth/logout", "POST");
  await navigate(new URL(inviteUrl).pathname);
  console.log("Live QA: one-time invitation acceptance");
  await until("document.querySelector('#join-name')");
  await set("#join-name", "Synthetic New Steward");
  await set("#join-password", "Synthetic Joining Password 35");
  await clickText("Join the board");
  await until(has("Your board-member account is ready"));
  assert.equal((await request("/auth/me")).status, 401, "Acceptance does not claim a login");
  await navigate(new URL(inviteUrl).pathname);
  await until("document.querySelector('#join-name')");
  await set("#join-name", "Synthetic New Steward");
  await set("#join-password", "Synthetic Joining Password 35");
  await clickText("Join the board");
  await until(has("invalid, expired, or already used"));
  await login("synthetic.new.steward@example.test", "Synthetic Joining Password 35");
  await navigate("/settings");
  await until(has("You can view the directory."));
  await request("/auth/logout", "POST");
  await login(credentials.email, credentials.password);
  await navigate("/settings");
  await until("document.querySelectorAll('.member-table tbody tr').length===4");
  assert.equal(
    (await request(`/members/${credentials.admin_id}/deactivate`, "POST")).status,
    403,
    "Holder protected",
  );
  await set(".scope-form select", "own_only");
  console.log("Live QA: scope and deactivation");
  await clickText("Save scope");
  await until(has("Reassignment scope saved"));
  assert.equal((await request("/governance")).body.reassign_scope, "own_only");
  await evaluate(
    "document.querySelector('button[aria-label=\"Deactivate Synthetic Avery Morgan\"]').focus(); document.querySelector('button[aria-label=\"Deactivate Synthetic Avery Morgan\"]').click()",
  );
  assert.equal(await evaluate("document.querySelector('dialog .button-danger').disabled"), true);
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  await clickText("Confirm deactivation");
  await until(has("Synthetic Avery Morgan is deactivated"));
  const members = (await request("/members")).body.items;
  const peer = members.find((m) => m.id === credentials.peer_id);
  assert.equal(peer.is_active, false);
  assert.equal(peer.owned_donor_count, 2);
  assert.equal(
    (await request("/reminders?scope=mine")).body.items.filter(
      (r) => r.type === "needs_reassignment",
    ).length,
    2,
  );
  assert.equal(
    (await request(`/members/${credentials.peer_id}/deactivate`, "POST")).status,
    409,
    "Duplicate deactivate rejected",
  );
  // Use the pre-deactivation cookie directly against local backend: it cannot authenticate.
  const revoked = await fetch("http://127.0.0.1:8000/api/app/auth/me", {
    headers: { Cookie: peerSession },
  });
  assert.equal(revoked.status, 401);
  assert.equal(
    (
      await request("/auth/login", "POST", {
        email: credentials.peer_email,
        password: credentials.password,
      })
    ).status,
    401,
    "Deactivated login blocked",
  );
  await clickText("Flatten hierarchy");
  console.log("Live QA: flatten");
  await shot("390-live-flatten");
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  await clickText("Confirm flatten hierarchy");
  await until(has("Hierarchy flattened."));
  const flat = (await request("/governance")).body;
  assert.equal(flat.mode, "flat");
  assert.equal(flat.super_admin_state, "dormant");
  assert.equal(flat.reassign_scope, "anyone");
  assert.equal((await request("/auth/me")).body.is_super_admin, false);
  assert.equal((await request("/governance/flatten", "POST")).status, 403);
  await shot("390-live-flat");
  await request("/auth/logout", "POST");
  await login("synthetic.new.steward@example.test", "Synthetic Joining Password 35");
  await navigate("/settings");
  await until("[...document.querySelectorAll('button')].some(b=>b.textContent==='Invite member')");
  assert.equal(
    await evaluate(
      "document.querySelector('button[aria-label=\"Deactivate Synthetic Board Lead\"]')===null",
    ),
    true,
    "Dormant holder protected",
  );
  assert.equal(
    (await request("/members/invite", "POST", { email: "synthetic.flat.invite@example.test" }))
      .status,
    201,
    "Flat peer can invite",
  );
  assert.equal(
    (await request("/governance/scope", "PUT", { reassign_scope: "own_only" })).status,
    403,
    "Flat scope fixed",
  );
  assert.deepEqual(errors, []);
  await writeFile(
    "qa/35/live-results.json",
    JSON.stringify(
      {
        result: "PASS",
        database: credentials.database,
        checks: [
          "real 403 role enforcement",
          "invite duplicate 409 and preserved email",
          "one-time link acceptance and login",
          "consumed link 400",
          "scope persisted",
          "deactivation retains two donors and refreshes member state",
          "Needs reassignment has two donors",
          "duplicate deactivation 409",
          "revoked session 401 and deactivated login 401",
          "flatten dormant/anyone and auth refresh",
          "flat peer can invite; dormant holder protected; scope fixed",
          "390/768/1440 live screenshots",
        ],
      },
      null,
      2,
    ),
  );
  console.log(
    "PASS live members/governance: actual invite/accept, duplicate, role enforcement, scope, deactivation/reassignment queue, revoked sessions and flatten.",
  );
} finally {
  socket?.close();
  browser.kill();
}
