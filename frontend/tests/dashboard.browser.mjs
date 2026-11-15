// Start Vite, then run: npm run test:dashboard
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9348;
const profile = resolve(".test-build/dashboard-browser");
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

  const owner = { id: 1, display_name: "Jordan Lee", is_active: true };
  const me = {
    ...owner,
    email: "jordan@example.test",
    is_super_admin: false,
    governance: { mode: "super_admin", reassign_scope: "own_only" },
  };
  const initial = [
    {
      type: "quarterly_due",
      action: "draft_update",
      donor_id: 1,
      donor_name: "Alex Rivera",
      due_date: "2026-10-01",
      overdue: true,
      owner,
    },
    {
      type: "thank_you_due",
      action: "draft_thank_you",
      donor_id: 2,
      donor_name: "Desert Learning Collective",
      due_date: "2026-11-14",
      overdue: true,
      owner,
      gift_id: 81,
    },
    {
      type: "next_step_due",
      action: "open_next_step",
      donor_id: 3,
      donor_name: "Maya Chen",
      due_date: "2026-11-17",
      overdue: false,
      owner,
      next_step_id: 91,
    },
    {
      type: "needs_reassignment",
      action: "reassign",
      donor_id: 4,
      donor_name: "Sunrise Community Fund",
      due_date: null,
      overdue: false,
      owner: { id: 9, display_name: "Taylor Morgan", is_active: false },
    },
  ];
  let items = structuredClone(initial);
  let status = 200;
  let waitMs = 0;
  let contactStatus = 201;
  let canAct = true;
  const requests = [];
  const routeErrors = [];
  const reply = (requestId, body, responseCode = 200) =>
    call("Fetch.fulfillRequest", {
      requestId,
      responseCode,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64"),
    });
  const handleRequest = async ({ requestId, request }) => {
    const url = new URL(request.url);
    const path = url.pathname.replace("/api/app", "");
    requests.push({ path, method: request.method, search: url.search });
    if (path === "/auth/me") return reply(requestId, me);
    if (path === "/reminders") {
      const captured = { items: structuredClone(items) };
      if (waitMs) await delay(waitMs);
      return reply(
        requestId,
        status === 200 ? captured : { error: { message: "Synthetic reminder failure" } },
        status,
      );
    }
    if (/^\/donors\/\d+$/.test(path)) {
      const id = Number(path.split("/").at(-1));
      return reply(requestId, {
        id,
        display_name: initial.find((r) => r.donor_id === id)?.donor_name,
        kind: "person",
        owner: id === 4 ? initial[3].owner : owner,
        can_act: canAct && id !== 4,
        contact_visible: canAct && id !== 4,
        can_reassign: false,
        email: null,
        phone: null,
        notes: null,
        contact_via: "Taylor Morgan",
        do_not_contact: false,
        statuses: [],
        total_12m_cents: 0,
        total_lifetime_cents: 0,
        created_at: "2026-01-01T12:00:00Z",
        recent_gifts: [],
        next_step_title: id === 3 ? "Share student showcase" : null,
        next_step_due: id === 3 ? "2026-11-17" : null,
      });
    }
    if (path.endsWith("/timeline")) return reply(requestId, { items: [] });
    if (path.endsWith("/interactions")) {
      if (contactStatus === 201)
        items = items.filter((r) => !(r.donor_id === 1 && r.type === "quarterly_due"));
      return reply(
        requestId,
        contactStatus === 201 ? { id: 101 } : { error: { message: "Contact forbidden" } },
        contactStatus,
      );
    }
    return reply(requestId, { error: { message: `Unexpected path ${path}` } }, 404);
  };
  const handler = socket.onmessage;
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Fetch.requestPaused")
      handleRequest(message.params).catch((e) => {
        // Chrome discards interceptions when React StrictMode aborts a query or
        // navigation cancels its request. All other protocol failures fail QA.
        if (!e.message.includes('"message":"Invalid InterceptionId."')) routeErrors.push(e);
      });
    handler(event);
  };
  await call("Fetch.enable", {
    patterns: [{ urlPattern: "*/api/app/*", requestStage: "Request" }],
  });
  const navigate = async (path = "/") => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until(
      "document.querySelector('.desk-dateline') || document.querySelector('.donor-dossier')",
    );
  };
  const viewport = (width, height) =>
    call("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  const shot = async (name) => {
    await mkdir("qa/33", { recursive: true });
    const { data } = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: true,
    });
    await writeFile(`qa/33/${name}.png`, Buffer.from(data, "base64"));
  };
  const text = () => evaluate("document.querySelector('main').textContent");
  const clickLink = (selector) =>
    evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const dashboard = async () => {
    await navigate();
    await until("document.querySelector('.reassignment-workspace')");
  };
  const refresh = async () => {
    await clickText("Refresh reminders");
    await until(
      "[...document.querySelectorAll('button')].some(b=>b.textContent==='Refresh reminders' && !b.disabled)",
    );
  };
  await viewport(1440, 900);
  waitMs = 700;
  await navigate();
  await until("document.querySelector('[aria-label=\"Loading your reminders\"]')");
  await shot("loading");
  waitMs = 0;
  await until("document.querySelectorAll('.todo-row').length===4");
  assert.deepEqual(
    await evaluate(
      "[...document.querySelectorAll('.todo-workspace .todo-row h3')].map(e=>e.textContent)",
    ),
    initial.slice(0, 3).map((r) => r.donor_name),
  );
  assert.ok((await text()).includes("2 overdue"));
  assert.ok((await text()).includes("Thank-you drafting is not available yet"));
  assert.ok((await text()).includes("Reassignment controls are not available yet"));
  assert.equal(requests.find((r) => r.path === "/reminders").search, "?scope=mine");
  for (const [width, height] of [
    [1440, 900],
    [768, 1024],
    [390, 844],
  ]) {
    await viewport(width, height);
    assert.equal(await evaluate("document.documentElement.scrollWidth <= innerWidth"), true);
    await shot(`${width}-dashboard`);
  }
  await evaluate("document.querySelector('.todo-filters button:nth-child(2)').focus()");
  await key("Enter", "Enter", 13);
  await until("document.querySelectorAll('.todo-workspace .todo-row').length===1");
  assert.ok((await text()).includes("Gift #81"));
  assert.equal(
    await evaluate("document.querySelectorAll('.reassignment-workspace .todo-row').length"),
    1,
  );
  await clickText("Next steps1");
  assert.equal(
    await evaluate("document.querySelector('.todo-action a').getAttribute('href')"),
    "/donors/3#next-step",
  );
  await clickLink(".todo-workspace .todo-action a");
  await until("document.activeElement.id==='next-step'");
  // Client-side round trip keeps the donor cached; the masthead must not steal focus.
  await evaluate("document.querySelector('a[href=\"/\"]').click()");
  await until("document.querySelector('.reassignment-workspace')");
  await clickLink('a[href="/donors/3#next-step"]');
  await until("document.activeElement.id==='next-step'");
  await dashboard();
  await clickLink('a[href="/donors/2#gift-history"]');
  await until("document.activeElement.id==='gift-history'");
  assert.equal(items.length, 4, "Opening gift history does not clear thank-you");
  await dashboard();
  await clickLink('a[href="/donors/4#relationship-owner"]');
  await until("document.activeElement.id==='relationship-owner'");
  assert.equal(await evaluate("document.querySelector('.contact-log-action > button')"), null);
  await dashboard();
  await clickLink('a[href="/donors/1#log-contact"]');
  await until("document.activeElement.id==='log-contact'");
  await clickText("Log contact");
  await evaluate("document.querySelector('input[value=call]').click()");
  contactStatus = 403;
  await clickText("Save contact");
  await until("document.querySelector('dialog[open] [role=alert]')");
  assert.equal(items.length, 4, "Failed contact does not complete a reminder");
  await dashboard();
  contactStatus = 201;
  await clickLink('a[href="/donors/1#log-contact"]');
  await until("document.activeElement.id==='log-contact'");
  await clickText("Log contact");
  await evaluate("document.querySelector('input[value=call]').click()");
  const before = requests.filter((r) => r.path === "/reminders").length;
  await clickText("Save contact");
  await until("!document.querySelector('dialog[open]')");
  await evaluate("document.querySelector('a[href=\"/\"]').click()");
  await until("document.querySelector('.reassignment-workspace')");
  assert.ok(requests.filter((r) => r.path === "/reminders").length > before);
  assert.equal(await evaluate("document.querySelectorAll('.todo-workspace .todo-row').length"), 2);
  // Failed refresh hides cached rows, especially after access is revoked.
  for (const code of [500, 501, 403, 401]) {
    status = code;
    await refresh();
    await until("document.querySelector('main [role=alert]')");
    assert.equal(await evaluate("document.querySelectorAll('.todo-row').length"), 0);
    if (code === 403) {
      assert.ok((await text()).includes("Access restricted"));
      await shot("390-forbidden");
    }
    if (code === 401) assert.ok((await text()).includes("Sign in"));
    status = 200;
    if (code === 401) await dashboard();
    else {
      await clickText("Try again");
      await until("document.querySelector('.reassignment-workspace')");
    }
  }
  items = [];
  await refresh();
  assert.ok((await text()).includes("Your follow-ups are up to date"));
  assert.ok((await text()).includes("Every relationship has an active owner"));
  await shot("390-empty");
  items = [initial[2]];
  await refresh();
  await clickText("Thank-you reminders0");
  assert.ok((await text()).includes("Nothing in this category"));
  await clickText("All reminders1");
  items = Array.from({ length: 205 }, (_, i) => ({
    ...initial[2],
    donor_id: 100 + i,
    next_step_id: 100 + i,
    donor_name: `Synthetic Community Learning Partnership ${i + 1}`,
  }));
  await refresh();
  assert.equal(
    await evaluate("document.querySelectorAll('.todo-workspace .todo-row').length"),
    205,
  );
  assert.equal(await evaluate("document.documentElement.scrollWidth<=innerWidth"), true);
  items = [
    {
      ...initial[0],
      donor_name:
        "The Synthetic Southwestern Community Foundation for Technology and Creative Learning Partnerships",
    },
    ...initial.slice(1),
  ];
  await refresh();
  await shot("390-long-name");
  await viewport(720, 450);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=innerWidth"), true);
  await shot("720-zoom-equivalent");
  await call("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('.todo-action a')).transitionDuration"),
    "0s",
  );
  assert.deepEqual(routeErrors, []);
  assert.deepEqual(errors, []);
  console.log(
    "PASS dashboard: categories/order, navigation/focus, server-confirmed contact refresh, failed writes, 401/403/500/501/retry, empty/filter states, 1/205 rows, responsive screenshots, keyboard and reduced motion.",
  );
} finally {
  socket?.close();
  browser.kill();
}
