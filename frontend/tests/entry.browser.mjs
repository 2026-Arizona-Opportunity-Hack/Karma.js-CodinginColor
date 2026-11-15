// Start Vite, then run: node tests/detail.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9345;
const profile = resolve(".test-build/entry-browser");
await mkdir(profile, { recursive: true });
const browser = spawn(
  process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe",
  [
    "--headless",
    "--disable-gpu",
    "--disable-extensions",
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
    for (let attempt = 0; attempt < 300; attempt++) {
      if (await evaluate(`Boolean(${expression})`)) return;
      await delay(100);
    }
    assert.fail(
      `Timed out: ${expression}; ${await evaluate("location.href + ' ' + document.body.innerText.slice(0,1000)")}`,
    );
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
  const owner = { id: 1, display_name: "Jordan Lee", is_active: true };
  const donor = {
    id: 1,
    kind: "person",
    display_name: "Alex Rivera",
    organization: "Community Learning Collective",
    first_name: "Alex",
    last_name: "Rivera",
    created_at: "2026-01-10T17:00:00Z",
    owner,
    contact_visible: true,
    can_act: true,
    can_reassign: false,
    email: "alex@example.org",
    phone: "+16025550123",
    notes: "Synthetic relationship for QA.",
    do_not_contact: false,
    statuses: [],
    total_12m_cents: 250000,
    total_lifetime_cents: 575000,
    last_gift_date: "2026-11-12",
    last_contact_date: null,
    next_step_title: null,
    next_step_due: null,
    recent_gifts: [],
  };
  const events = [];
  const records = [donor];
  const requests = [];
  const routeErrors = [];
  let failure = 0;
  let duplicate = false;
  let saveDelay = 0;
  let programsUnavailable = false;
  const reply = (requestId, body, responseCode = 200) =>
    call("Fetch.fulfillRequest", {
      requestId,
      responseCode,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64"),
    });
  const handle = async ({ requestId, request }) => {
    const url = new URL(request.url);
    const path = url.pathname.replace("/api/app", "");
    const body = request.postData && JSON.parse(request.postData);
    requests.push({ path, method: request.method, body, headers: request.headers });
    if (request.method !== "GET") {
      await delay(saveDelay);
      if (failure === -1)
        return call("Fetch.failRequest", { requestId, errorReason: "InternetDisconnected" });
      if (failure === 422)
        return reply(
          requestId,
          { detail: [{ loc: ["body", "email"], msg: "Email needs a valid domain." }] },
          422,
        );
      if (failure)
        return reply(
          requestId,
          { error: { code: "test_error", message: "Synthetic server validation failure." } },
          failure,
        );
      if (path === "/donors" && duplicate && !body.confirm_new)
        return reply(
          requestId,
          {
            error: { code: "possible_duplicate", message: "Possible existing donor" },
            candidates: [
              { donor_id: 1, display_name: donor.display_name, owner, match_reason: "email" },
            ],
          },
          409,
        );
      if (path === "/donors") {
        const created = { ...donor, ...body, id: records.length + 1 };
        records.push(created);
        return reply(requestId, created, 201);
      }
      if (path === "/donors/1" && request.method === "PATCH") {
        Object.assign(donor, body);
        return reply(requestId, donor);
      }
      if (path === "/donors/1/gifts") {
        const gift = {
          id: 50 + events.length,
          donor_id: 1,
          donor_name: donor.display_name,
          source: "manual",
          attribution: "linked",
          ...body,
          fee_cents: 0,
          net_cents: body.gross_cents,
          program: body.program_id === 7 ? "AI Academy" : "General",
        };
        donor.total_lifetime_cents += body.gross_cents;
        donor.total_12m_cents += body.gross_cents;
        donor.recent_gifts.unshift(gift);
        events.unshift({
          kind: "gift",
          at: `${body.gift_date}T12:00:00Z`,
          title: "Manual gift received",
          amount_cents: body.gross_cents,
          entity_id: gift.id,
        });
        return reply(requestId, gift, 201);
      }
      throw new Error(`Unexpected write ${request.method} ${path}`);
    }
    if (path === "/auth/me")
      return reply(requestId, {
        ...owner,
        email: "jordan@example.org",
        is_super_admin: false,
        governance: { mode: "flat", reassign_scope: "anyone" },
      });
    if (path === "/donors")
      return reply(requestId, { items: records, total: records.length, page: 1, page_size: 20 });
    if (path === "/donors/1") return reply(requestId, donor);
    if (path === "/donors/1/timeline") return reply(requestId, { items: events });
    if (path === "/members") return reply(requestId, { items: [owner] });
    if (path === "/programs" && programsUnavailable)
      return reply(
        requestId,
        { error: { code: "not_implemented", message: "Not available yet" } },
        501,
      );
    if (path === "/programs")
      return reply(requestId, {
        items: [
          { id: 7, name: "AI Academy", slug: "ai-academy", is_active: true },
          { id: 8, name: "Inactive", slug: "old", is_active: false },
        ],
      });
    return reply(requestId, { error: { message: "Unavailable" } }, 404);
  };
  const prior = socket.onmessage;
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Fetch.requestPaused")
      handle(message.params).catch((error) => {
        // Navigating away aborts pending GETs; CDP can no longer fulfill their interception.
        if (
          message.params.request.method === "GET" &&
          error.message.includes("Invalid InterceptionId")
        )
          return;
        routeErrors.push(error.message);
      });
    prior(event);
  };
  await call("Fetch.enable", { patterns: [{ urlPattern: "*/api/app/*" }] });
  await call("Network.setCookie", {
    name: "cic_csrf",
    value: "synthetic-csrf",
    url: "http://127.0.0.1:5173",
  });
  const fill = (selector, value) =>
    evaluate(
      `(() => { const n=document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(Object.getPrototypeOf(n),'value').set.call(n,${JSON.stringify(value)}); n.dispatchEvent(new Event('input',{bubbles:true})); n.dispatchEvent(new Event('change',{bubbles:true})); })()`,
    );
  const open = async (path = "/donors") => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until(
      path === "/donors"
        ? "document.querySelector('.directory')"
        : "document.querySelector('.giving-summary')",
    );
  };
  const shot = async (name) => {
    await delay(250);
    await evaluate("document.querySelector('dialog[open]').scrollTop = 0");
    if (name.endsWith("-fields") || name.endsWith("-context"))
      await evaluate(
        "document.querySelector('dialog[open]').scrollTop = document.querySelector('dialog[open]').scrollHeight",
      );
    await mkdir("qa/21", { recursive: true });
    const result = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    await writeFile(`qa/21/${name}.png`, Buffer.from(result.data, "base64"));
  };
  const submit = () => evaluate("document.querySelector('dialog[open] form').requestSubmit()");
  const saved = () => until("!document.querySelector('dialog[open]')");
  const errorShown = () => until("document.querySelector('dialog[open] [role=alert]')");
  for (const width of [1440, 768, 390]) {
    await call("Emulation.setDeviceMetricsOverride", {
      width,
      height: width === 390 ? 844 : width === 768 ? 1024 : 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await open();
    await clickText("Create donor");
    await until("document.querySelector('dialog[open]')");
    assert.equal(await evaluate("document.activeElement.tagName"), "H2");
    await submit();
    await errorShown();
    assert.equal(
      requests.filter((r) => r.method === "POST").length,
      width === 1440 ? 0 : width === 768 ? 2 : 4,
    );
    await fill("#entry-display_name", `Synthetic Learning Fund ${width}`);
    await fill(
      "#entry-kind",
      width === 1440 ? "funder" : width === 768 ? "organization" : "person",
    );
    await fill("#entry-organization", "Community Learning Collective");
    await fill("#entry-email", `fund${width}@example.org`);
    await shot(`${width}-create`);
    if (width === 390) await shot("390-create-context");
    assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth"));
    assert.ok(await evaluate("document.querySelector('dialog[open]').scrollWidth <= innerWidth"));
    const before = requests.filter((r) => r.method === "POST").length;
    saveDelay = 200;
    await evaluate(
      "document.querySelector('dialog[open] form').requestSubmit();document.querySelector('dialog[open] form').requestSubmit()",
    );
    await saved();
    assert.equal(
      requests.filter((r) => r.method === "POST").length,
      before + 1,
      "Synchronous double submits send once",
    );
    assert.ok(
      await evaluate("document.activeElement.textContent.includes('Create donor')"),
      "Focus restored",
    );
    assert.ok(
      await evaluate(
        `document.querySelector('.directory').textContent.includes('Synthetic Learning Fund ${width}')`,
      ),
      "Directory refetched",
    );
    saveDelay = 0;
    await open("/donors/1");
    await clickText("Edit donor");
    assert.equal(await evaluate("document.querySelector('#entry-email').value"), donor.email);
    assert.equal(await evaluate("document.querySelector('#entry-kind').disabled"), true);
    await fill("#entry-organization", `Synthetic employer ${width}`);
    await shot(`${width}-edit`);
    await submit();
    await saved();
    assert.ok(
      await evaluate(
        `document.querySelector('.page-masthead').textContent.includes('Synthetic employer ${width}')`,
      ),
    );
    await clickText("Add gift");
    await fill("#entry-amount", "0.29");
    await fill("#entry-gift_date", "2026-11-14");
    await until("document.querySelector('#entry-program_id option[value=\"7\"]')");
    await fill("#entry-program_id", "7");
    assert.equal(
      await evaluate("document.querySelector('#entry-program_id option[value=\"8\"]')"),
      null,
    );
    assert.ok(
      await evaluate(
        "document.querySelector('dialog[open]').textContent.includes('Gift editing and gift notes are not available')",
      ),
    );
    assert.equal(await evaluate("document.querySelector('dialog[open] textarea')"), null);
    await shot(`${width}-gift`);
    if (width === 390) await shot("390-gift-fields");
    const oldTotal = donor.total_lifetime_cents;
    await submit();
    await saved();
    assert.equal(donor.total_lifetime_cents, oldTotal + 29);
    assert.ok(
      await evaluate(
        "document.querySelector('#relationship-timeline').textContent.includes('Manual gift received')",
      ),
      "Timeline refreshed",
    );
    assert.ok(
      await evaluate("document.querySelector('.gift-list').textContent.includes('$0.29')"),
      "Gift list refreshed",
    );
    const lastGift = requests.filter((r) => r.path.endsWith("/gifts")).at(-1);
    assert.deepEqual(lastGift.body, { gift_date: "2026-11-14", gross_cents: 29, program_id: 7 });
    assert.equal(lastGift.headers["X-CSRF-Token"], "synthetic-csrf");
  }
  await open();
  await clickText("Create donor");
  await fill("#entry-display_name", "Alex Rivera Jr.");
  await fill("#entry-email", "alex@example.org");
  duplicate = true;
  await submit();
  await errorShown();
  await until("document.querySelector('.entry-conflicts')");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] button[type=submit]').disabled"),
    true,
  );
  assert.ok(
    await evaluate(
      "document.querySelector('.entry-conflicts a').getAttribute('href') === '/donors/1'",
    ),
  );
  await shot("390-duplicate");
  await evaluate("document.querySelector('.entry-conflicts input').click()");
  await fill("#entry-display_name", "Alex Separate");
  assert.equal(
    await evaluate("document.querySelector('.entry-conflicts')"),
    null,
    "Changing values resets duplicate consent",
  );
  await submit();
  await until("document.querySelector('.entry-conflicts')");
  await evaluate("document.querySelector('.entry-conflicts input').click()");
  await submit();
  await saved();
  assert.equal(requests.filter((r) => r.method === "POST").at(-1).body.confirm_new, true);
  assert.equal(donor.display_name, "Alex Rivera", "Existing donor not overwritten");
  duplicate = false;
  await open("/donors/1");
  for (const status of [400, 409, 422, 500, -1, 401, 403, 404, 501]) {
    await clickText("Edit donor");
    await fill("#entry-notes", `Preserved synthetic draft ${status}`);
    failure = status;
    await submit();
    await errorShown();
    assert.equal(
      await evaluate("document.querySelector('#entry-notes').value"),
      `Preserved synthetic draft ${status}`,
    );
    await until("document.activeElement.getAttribute('role') === 'alert'");
    if (status === 422)
      assert.equal(
        await evaluate("document.querySelector('#entry-email').getAttribute('aria-invalid')"),
        "true",
      );
    if ([401, 403, 404, 501].includes(status))
      assert.equal(
        await evaluate("document.querySelector('dialog[open] button[type=submit]').disabled"),
        true,
      );
    if ([500, -1].includes(status)) {
      assert.equal(
        await evaluate("document.querySelector('dialog[open] button[type=submit]').disabled"),
        true,
      );
      await evaluate("document.querySelector('dialog[open] .entry-check input').click()");
    }
    if (status === 422) await shot("390-server-validation");
    failure = 0;
    if (![401, 403, 404, 501].includes(status)) {
      await submit();
      await saved();
    } else {
      // Native discard confirmation must be explicit; accept it through CDP.
      const accepting = new Promise((resolve) => {
        const previous = socket.onmessage;
        socket.onmessage = (event) => {
          if (JSON.parse(event.data).method === "Page.javascriptDialogOpening") {
            socket.onmessage = previous;
            call("Page.handleJavaScriptDialog", { accept: true }).then(resolve);
          }
          previous(event);
        };
      });
      await clickText("Cancel");
      await accepting;
      await saved();
      await open("/donors/1");
    }
  }
  await clickText("Add gift");
  for (const invalid of ["0", "-10", "1.234", "1e3", "10000000.01"]) {
    await fill("#entry-amount", invalid);
    await submit();
    await errorShown();
    assert.equal(
      await evaluate("document.querySelector('#entry-amount').getAttribute('aria-invalid')"),
      "true",
    );
  }
  await fill("#entry-amount", "10.01");
  await fill("#entry-gift_date", "2099-01-01");
  await submit();
  await errorShown();
  assert.equal(
    await evaluate("document.querySelector('#entry-gift_date').getAttribute('aria-invalid')"),
    "true",
  );
  await fill("#entry-gift_date", "2026-11-14");
  failure = -1;
  await submit();
  await errorShown();
  assert.equal(await evaluate("document.querySelector('#entry-amount').value"), "10.01");
  assert.equal(await evaluate("document.querySelector('#entry-gift_date').value"), "2026-11-14");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] button[type=submit]').disabled"),
    true,
  );
  failure = 0;
  await evaluate("document.querySelector('dialog[open] .entry-check input').click()");
  await submit();
  await saved();
  assert.equal(requests.filter((r) => r.path.endsWith("/gifts")).at(-1).body.gross_cents, 1001);
  // A navigation creates a fresh isolated browser state for permission checks.
  programsUnavailable = true;
  donor.can_act = false;
  donor.contact_visible = false;
  await open("/donors/1");
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('button')].some(b => ['Edit donor','Add gift'].includes(b.textContent.trim()))",
    ),
    false,
  );
  assert.equal(
    await evaluate("document.body.textContent.includes('Preserved synthetic draft')"),
    false,
  );
  donor.can_act = true;
  donor.contact_visible = true;
  donor.do_not_contact = true;
  await open("/donors/1");
  await clickText("Add gift");
  await until("document.querySelector('#entry-program-help').textContent.includes('unavailable')");
  assert.equal(await evaluate("document.querySelectorAll('#entry-program_id option').length"), 1);
  await fill("#entry-amount", "125.50");
  await fill("#entry-gift_date", "2026-11-14");
  await shot("390-gift-default-program");
  await shot("390-gift-default-program-fields");
  await submit();
  await saved();
  assert.equal(requests.filter((r) => r.path.endsWith("/gifts")).at(-1).body.program_id, null);
  await clickText("Add gift");
  assert.ok(
    await evaluate(
      "document.querySelector('dialog[open]').textContent.includes('Anonymous Benevity gifts cannot be attached')",
    ),
  );
  await call("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('dialog[open]')).animationDuration"),
    "0s",
  );
  // Unchanged form can close with Escape; focus returns to its opener.
  await evaluate("document.querySelector('dialog[open] button[type=submit]').focus()");
  await key("Tab", "Tab", 9);
  assert.equal(await evaluate("document.activeElement.getAttribute('aria-label')"), "Close sheet");
  await key("Escape", "Escape", 27);
  await saved();
  assert.ok(await evaluate("document.activeElement.textContent.includes('Add gift')"));
  assert.deepEqual(routeErrors, []);
  assert.deepEqual(errors, []);
  console.log(
    "PASS: create/edit/gift journeys at 390/768/1440; decimal cents/date/program/CSRF; duplicate review; validation, conflict, permissions, network recovery, draft retention, single submission, cache refresh, focus, privacy, unsupported gift edit/notes and Benevity safeguards.",
  );
} finally {
  socket?.close();
  browser.kill();
}
