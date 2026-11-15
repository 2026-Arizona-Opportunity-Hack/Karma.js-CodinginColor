// Start Vite, then run: npm run test:members
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9355;
const profile = resolve(`.test-build/members-browser-${process.pid}`);
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

  const me = {
    id: 1,
    display_name: "Synthetic Jordan Lee",
    email: "jordan@example.test",
    is_super_admin: true,
    governance: { mode: "super_admin", reassign_scope: "own_only" },
  };
  let gov = {
    ...me.governance,
    super_admin_state: "active",
    super_admin: { id: 1, display_name: me.display_name, is_active: true },
    updated_at: "2026-11-15T12:00:00Z",
  };
  const member = (id, name, active = true) => ({
    id,
    display_name: name,
    email: `member${id}@example.test`,
    is_active: active,
    is_super_admin: id === 1,
    owned_donor_count: id === 2 ? 12 : 3,
    created_at: "2026-11-01T12:00:00Z",
    deactivated_at: active ? null : "2026-11-14T12:00:00Z",
  });
  let items = [
    member(1, me.display_name),
    member(2, "Synthetic Avery Morgan"),
    member(3, "Synthetic Former Steward", false),
  ];
  let fail = 0;
  let readFail = 0;
  let governanceFail = 0;
  let readDelay = 0;
  let joined = false;
  const requests = [];
  const routeErrors = [];
  const reply = (requestId, body, responseCode = 200) =>
    call("Fetch.fulfillRequest", {
      requestId,
      responseCode,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64"),
    });
  const handle = async ({ requestId, request }) => {
    const path = new URL(request.url).pathname.replace("/api/app", "");
    requests.push({ path, method: request.method, body: request.postData });
    if (path === "/auth/me") return reply(requestId, me);
    if (path === "/members" || path === "/governance") {
      if (readDelay) await delay(readDelay);
      const status = path === "/members" ? readFail : governanceFail;
      return reply(
        requestId,
        status
          ? { error: { message: "Synthetic read failure" } }
          : path === "/members"
            ? { items }
            : gov,
        status || 200,
      );
    }
    if (fail) return reply(requestId, { error: { message: `Synthetic failure ${fail}` } }, fail);
    if (path === "/members/invite")
      return reply(
        requestId,
        {
          id: 44,
          email: JSON.parse(request.postData).email,
          invite_url: "http://127.0.0.1:5173/invite/synthetic-private-link",
          expires_at: "2026-11-18T18:00:00Z",
        },
        201,
      );
    if (path.endsWith("/deactivate")) {
      items[1].is_active = false;
      items[1].deactivated_at = "2026-11-15T12:00:00Z";
      return reply(requestId, items[1]);
    }
    if (path === "/governance/scope") {
      gov.reassign_scope = JSON.parse(request.postData).reassign_scope;
      me.governance.reassign_scope = gov.reassign_scope;
      return reply(requestId, gov);
    }
    if (path === "/governance/nominations") return reply(requestId, null);
    if (path === "/governance/flatten") {
      gov = { ...gov, mode: "flat", super_admin_state: "dormant", reassign_scope: "anyone" };
      me.is_super_admin = false;
      me.governance = { mode: "flat", reassign_scope: "anyone" };
      return reply(requestId, gov);
    }
    if (path.startsWith("/auth/invite/")) {
      if (joined) return reply(requestId, { error: { message: "Invalid link" } }, 400);
      joined = true;
      return reply(requestId, me, 201);
    }
    throw new Error(`Unexpected API request ${path}`);
  };
  const original = socket.onmessage;
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Fetch.requestPaused")
      void handle(message.params).catch((e) => {
        // Navigating away deliberately cancels the slow-loading test requests.
        if (!e.message.includes("Invalid InterceptionId")) routeErrors.push(e.message);
      });
    original(event);
  };
  await call("Fetch.enable", { patterns: [{ urlPattern: "*/api/app/*" }] });
  const navigate = async (path = "/settings") => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until("document.querySelector('h1')");
  };
  const ready = () =>
    until(
      "document.querySelectorAll('.member-table tbody tr').length===3 && [...document.querySelectorAll('button')].some(b=>b.textContent==='Invite member' && !b.disabled)",
    );
  const set = (selector, value) =>
    evaluate(
      `{const el=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(el instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set; setter.call(el,${JSON.stringify(value)}); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));}`,
    );
  const has = (text) => `document.body.textContent.includes(${JSON.stringify(text)})`;
  const shot = async (name) => {
    await delay(240);
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: await evaluate(
        "!document.querySelector('dialog[open]') && document.querySelectorAll('.member-table tbody tr').length < 30",
      ),
    });
    await writeFile(`qa/35/${name}.png`, Buffer.from(data, "base64"));
  };
  const viewport = async (width, height) => {
    await call("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await delay(200);
    assert.equal(
      await evaluate("document.documentElement.scrollWidth<=innerWidth"),
      true,
      `No overflow at ${width}`,
    );
  };
  const writes = () => requests.filter((r) => r.method !== "GET").length;
  await mkdir("qa/35", { recursive: true });
  await navigate();
  await ready();
  assert.equal(
    await evaluate("document.querySelectorAll('button[aria-label^=Deactivate]').length"),
    1,
    "No self, inactive, or holder deactivation",
  );
  // Remove-my-role needs the typed word; nothing is written until then (GOV-3).
  await clickText("Remove my super admin role");
  await until("document.querySelector('dialog[open] input')");
  assert.equal(await evaluate(has("you stay a board member")), true, "Explains the outcome");
  assert.equal(
    await evaluate("document.querySelector('dialog .button-danger').disabled"),
    true,
    "REMOVE not typed yet",
  );
  await set("dialog input", "REMOVE");
  assert.equal(
    await evaluate("document.querySelector('dialog .button-danger').disabled"),
    false,
    "REMOVE typed",
  );
  await clickText("Cancel");
  for (const [w, h] of [
    [1440, 900],
    [768, 1024],
    [390, 844],
  ]) {
    await viewport(w, h);
    await shot(`${w}-settings`);
  }
  await clickText("Invite member");
  await until("document.querySelector('dialog[open]')");
  assert.equal(
    await evaluate("document.activeElement.tagName"),
    "H2",
    "Sheet announces its heading first",
  );
  await call("Input.dispatchKeyEvent", {
    type: "keyDown",
    key: "Tab",
    code: "Tab",
    windowsVirtualKeyCode: 9,
    modifiers: 8,
  });
  await call("Input.dispatchKeyEvent", {
    type: "keyUp",
    key: "Tab",
    code: "Tab",
    windowsVirtualKeyCode: 9,
  });
  assert.equal(
    await evaluate("document.activeElement.textContent.trim()"),
    "Cancel",
    "Reverse Tab wraps inside sheet",
  );
  await key("Tab", "Tab", 9);
  assert.equal(
    await evaluate("document.activeElement.getAttribute('aria-label')"),
    "Close sheet",
    "Forward Tab wraps inside sheet",
  );
  await key("Escape", "Escape", 27);
  await until("!document.querySelector('dialog[open]')");
  assert.equal(
    await evaluate("document.activeElement.textContent.trim()"),
    "Invite member",
    "Escape restores opener",
  );
  await clickText("Invite member");
  const before = writes();
  await clickText("Create invitation link");
  assert.equal(writes(), before, "Native required email blocks write");
  await set("dialog input[type=email]", "new.steward@example.test");
  for (const status of [409, 422, 500, 501, 401, 403]) {
    fail = status;
    await clickText("Create invitation link");
    await until(
      "document.querySelector('dialog [role=alert]') && !document.querySelector('dialog').querySelector('.quick-note-footer button').disabled".replace(
        " && !document.querySelector('dialog').querySelector('.quick-note-footer button').disabled",
        status === 401 || status === 403
          ? ""
          : " && !document.querySelector('dialog').querySelector('.quick-note-footer button').disabled",
      ),
    );
    assert.equal(
      await evaluate("document.querySelector('dialog input[type=email]').value"),
      "new.steward@example.test",
    );
    if (status === 500) await shot("390-invite-error");
    if ([401, 403].includes(status)) {
      await clickText("Cancel");
      fail = 0;
      await navigate();
      await ready();
      await clickText("Invite member");
      await set("dialog input[type=email]", "new.steward@example.test");
    }
  }
  fail = 0;
  await clickText("Create invitation link");
  await until(has("No email was sent."));
  assert.equal(
    await evaluate("document.querySelector('dialog input[readonly]').value"),
    "http://127.0.0.1:5173/invite/synthetic-private-link",
  );
  await shot("390-invitation");
  await clickText("Done");
  assert.equal(
    await evaluate("document.body.textContent.includes('synthetic-private-link')"),
    false,
    "Link cleared after closing",
  );
  await clickText("Deactivate");
  const count = writes();
  await clickText("Confirm deactivation");
  assert.equal(writes(), count, "Deactivation requires confirmation");
  await shot("390-deactivate");
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  fail = 500;
  await clickText("Confirm deactivation");
  await until("document.querySelector('dialog [role=alert]')");
  await until("!document.querySelector('dialog input[type=checkbox]').checked");
  assert.equal(
    await evaluate("document.querySelector('dialog .button-danger').disabled"),
    true,
    "Failure resets confirmation",
  );
  fail = 0;
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  await clickText("Confirm deactivation");
  await until("!document.querySelector('dialog[open]')");
  await until(has("Synthetic Avery Morgan is deactivated"));
  assert.equal(
    await evaluate("document.querySelectorAll('button[aria-label^=Deactivate]').length"),
    0,
  );
  await set(".scope-form select", "anyone");
  fail = 500;
  await clickText("Save scope");
  await until(
    "document.querySelector('.save-error') && [...document.querySelectorAll('button')].some(b=>b.textContent==='Save scope' && !b.disabled)",
  );
  assert.equal(
    await evaluate("document.querySelector('.scope-form select').value"),
    "anyone",
    "Scope choice survives server failure",
  );
  fail = 0;
  await clickText("Save scope");
  await until(has("Reassignment scope saved"));
  assert.equal(
    requests.findLast((r) => r.path === "/governance/scope").body,
    '{"reassign_scope":"anyone"}',
  );
  await clickText("Flatten hierarchy");
  const flattenCount = writes();
  await clickText("Confirm flatten hierarchy");
  assert.equal(writes(), flattenCount);
  assert.equal(await evaluate(has("This cannot be undone in the app.")), true);
  for (const [w, h] of [
    [390, 844],
    [768, 1024],
    [1440, 900],
  ]) {
    await viewport(w, h);
    await shot(`${w}-flatten`);
  }
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  fail = 500;
  await clickText("Confirm flatten hierarchy");
  await until(
    "document.querySelector('dialog [role=alert]') && !document.querySelector('dialog input[type=checkbox]').disabled",
  );
  assert.equal(
    await evaluate("document.querySelector('dialog input[type=checkbox]').checked"),
    false,
    "Flatten failure requires renewed confirmation",
  );
  fail = 0;
  await evaluate("document.querySelector('dialog input[type=checkbox]').click()");
  await clickText("Confirm flatten hierarchy");
  await until(has("Hierarchy flattened."));
  assert.equal(await evaluate("document.querySelector('.scope-form')===null"), true);
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('button')].some(b=>b.textContent==='Flatten hierarchy')",
    ),
    false,
  );
  await until("[...document.querySelectorAll('button')].some(b=>b.textContent==='Invite member')");
  await shot("1440-flat");
  // Flat again: anyone can nominate, and nothing is sent until a member is chosen (GOV-2).
  await viewport(390, 844);
  await clickText("Nominate super admin");
  await until("document.querySelector('dialog[open] select')");
  assert.equal(
    await evaluate("document.querySelector('dialog .quick-note-footer .button').disabled"),
    true,
    "Choose a member first",
  );
  await set("dialog select", "1");
  assert.equal(
    await evaluate("document.querySelector('dialog .quick-note-footer .button').disabled"),
    false,
  );
  await shot("390-nominate");
  await clickText("Cancel");
  // Dormant holder remains protected, while a regular active peer can be deactivated in flat mode.
  items[1].is_active = true;
  me.id = 2;
  me.display_name = items[1].display_name;
  await navigate();
  await ready();
  assert.equal(
    await evaluate(
      "document.querySelector('button[aria-label=\"Deactivate Synthetic Jordan Lee\"]')===null",
    ),
    true,
  );
  me.id = 4;
  await navigate();
  await ready();
  assert.equal(
    await evaluate("document.querySelectorAll('button[aria-label^=Deactivate]').length"),
    1,
  );
  // Read-only member under active administration sees neither management nor governance writes.
  gov.mode = "super_admin";
  gov.super_admin_state = "active";
  gov.reassign_scope = "own_only";
  me.governance = { mode: "super_admin", reassign_scope: "own_only" };
  await navigate();
  await until(has("You can view the directory."));
  assert.equal(
    await evaluate(
      "document.querySelectorAll('button[aria-label^=Deactivate],.scope-form').length",
    ),
    0,
  );
  await viewport(390, 844);
  await shot("390-restricted");
  // Search and large directory, no-match and truly empty states.
  await set("input[type=search]", "not-a-person");
  await until(has("No matching members"));
  items = [];
  await navigate();
  await until(has("Your circle starts here"));
  await shot("390-empty");
  items = Array.from({ length: 205 }, (_, i) =>
    member(
      i + 1,
      i === 0
        ? "Synthetic Southwestern Community Partnership for Creative Learning and Technology"
        : `Synthetic Steward ${i + 1}`,
    ),
  );
  await navigate();
  await until("document.querySelectorAll('.member-table tbody tr').length===205");
  await viewport(390, 844);
  await shot("390-density");
  await viewport(720, 450);
  await shot("720-zoom-equivalent");
  readFail = 500;
  await navigate();
  await until(has("Synthetic read failure"));
  readFail = 0;
  await clickText("Try again");
  await until("document.querySelectorAll('.member-table tbody tr').length===205");
  governanceFail = 403;
  await navigate();
  await until(has("This view isn’t available to you"));
  assert.equal(
    await evaluate(
      "document.querySelectorAll('button[aria-label^=Deactivate],.scope-form').length",
    ),
    0,
  );
  governanceFail = 0;
  readDelay = 1000;
  await navigate();
  await until("document.querySelector('[aria-label=\"Loading members\"]')");
  await shot("390-loading");
  readDelay = 0;
  await navigate("/invite/synthetic-private-link");
  await until("document.querySelector('#join-name')");
  await set("#join-name", "Synthetic New Steward");
  await set("#join-password", "Synthetic Password 123");
  await clickText("Join the board");
  await until(has("Your board-member account is ready"));
  assert.equal(await evaluate("location.pathname"), "/invite/accepted");
  await shot("720-joined");
  await navigate("/invite/synthetic-private-link");
  await until("document.querySelector('#join-name')");
  await set("#join-name", "Synthetic New Steward");
  await set("#join-password", "Synthetic Password 123");
  await clickText("Join the board");
  await until(has("invalid, expired, or already used"));
  assert.equal(await evaluate("document.querySelector('#join-password').disabled"), true);
  assert.deepEqual(routeErrors, []);
  assert.deepEqual(errors, []);
  await writeFile(
    "qa/35/browser-results.json",
    JSON.stringify(
      {
        result: "PASS",
        requests: requests.map(({ path, method }) => ({
          path: path.startsWith("/auth/invite/") ? "/auth/invite/[redacted]/accept" : path,
          method,
        })),
        checks: [
          "permissions: active/flat/dormant/read-only",
          "native validation",
          "invitation and acceptance",
          "401/403/409/422/500/501 recovery",
          "deactivation confirmation and refresh",
          "scope persistence",
          "flatten safeguards and permission refresh",
          "keyboard Escape and focus restore",
          "390/768/1440/720 responsive screenshots",
          "0/3/205 members and long names",
          "loading, empty, search, read retry",
        ],
      },
      null,
      2,
    ),
  );
  console.log(
    "PASS members/governance browser: permissions, invitations, deactivation, scope, flatten safeguards, errors, keyboard, responsive states and 205 records.",
  );
} finally {
  socket?.close();
  browser.kill();
}
