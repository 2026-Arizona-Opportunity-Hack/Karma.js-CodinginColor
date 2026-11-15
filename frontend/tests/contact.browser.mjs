// Start Vite, then run: node tests/detail.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9341;
const profile = resolve(".test-build/contact-browser");
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
  const donor = {
    id: 1,
    kind: "person",
    display_name: "Alex Rivera",
    organization: "Community Learning Collective",
    created_at: "2026-01-10T17:00:00Z",
    owner,
    contact_visible: true,
    can_act: true,
    can_reassign: false,
    email: "alex@example.test",
    phone: null,
    notes: null,
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
  const requests = [];
  let failure = 0;
  let waitMs = 0;
  let releaseSave;
  let sequence = 100;
  let activeStep;
  let timelineFailure = false;
  const reply = (requestId, body, status = 200) =>
    call("Fetch.fulfillRequest", {
      requestId,
      responseCode: status,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64"),
    });
  const handleRequest = async ({ requestId, request }) => {
    const path = new URL(request.url).pathname.replace("/api/app", "");
    requests.push({
      path,
      method: request.method,
      headers: request.headers,
      body: request.postData && JSON.parse(request.postData),
    });
    if (request.method !== "GET") {
      if (waitMs === -1)
        await new Promise((resolve) => {
          releaseSave = resolve;
        });
      else if (waitMs) await delay(waitMs);
      if (failure === -1)
        return call("Fetch.failRequest", { requestId, errorReason: "InternetDisconnected" });
      if (failure)
        return reply(
          requestId,
          {
            error: {
              message:
                failure === 422 ? "Please check the form and try again." : "Synthetic save failure",
            },
          },
          failure,
        );
    }
    if (path === "/auth/me")
      return reply(requestId, {
        ...owner,
        email: "jordan@example.test",
        is_super_admin: false,
        governance: { mode: "flat", reassign_scope: "own_only" },
      });
    if (path === "/donors/1/timeline")
      return timelineFailure
        ? reply(requestId, { error: { message: "Timeline unavailable" } }, 500)
        : reply(requestId, { items: events });
    if (path === "/donors/1") return reply(requestId, donor);
    if (path === "/donors/1/interactions") {
      const body = JSON.parse(request.postData);
      donor.last_contact_date = body.occurred_on;
      events.unshift({
        kind: body.kind === "note" ? "note" : "contact",
        entity_id: ++sequence,
        title: body.kind[0].toUpperCase() + body.kind.slice(1),
        at: `${body.occurred_on}T19:00:00Z`,
        detail: body.summary,
        by: owner.display_name,
      });
      return reply(requestId, { ...body, id: sequence, donor_id: 1, user: owner }, 201);
    }
    if (path === "/donors/1/next-step") {
      const body = JSON.parse(request.postData);
      activeStep = { ...body, id: ++sequence, donor_id: 1, status: "open" };
      donor.next_step_title = body.title;
      donor.next_step_due = body.due_date;
      events.unshift({
        kind: "next_step",
        entity_id: sequence,
        title: `Next step: ${body.title}`,
        at: new Date().toISOString(),
        detail: `Due ${body.due_date}`,
      });
      return reply(requestId, activeStep);
    }
    if (path === `/next-steps/${activeStep?.id}/done`) {
      donor.next_step_title = donor.next_step_due = null;
      activeStep.status = "done";
      events.unshift({
        kind: "note",
        entity_id: ++sequence,
        title: "Note",
        at: new Date().toISOString(),
        detail: `Completed next step: ${activeStep.title}`,
      });
      return reply(requestId, activeStep);
    }
    return reply(requestId, { error: { message: `Unexpected path: ${path}` } }, 404);
  };
  const routeErrors = [];
  const handler = socket.onmessage;
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Fetch.requestPaused")
      handleRequest(message.params).catch((error) => routeErrors.push(error));
    handler(event);
  };
  await call("Fetch.enable", {
    patterns: [{ urlPattern: "*/api/app/*", requestStage: "Request" }],
  });
  await call("Page.addScriptToEvaluateOnNewDocument", {
    source: "document.cookie='cic_csrf=synthetic-csrf; path=/';",
  });
  const viewport = (width, height) =>
    call("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
  const refresh = async () => {
    const previous = requests.filter((r) => r.path === "/donors/1").length;
    await evaluate("window.dispatchEvent(new Event('visibilitychange'))");
    for (
      let i = 0;
      i < 100 && requests.filter((r) => r.path === "/donors/1").length === previous;
      i++
    )
      await delay(50);
    await delay(200);
  };
  const fill = (selector, value) =>
    evaluate(`(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto,'value').set.call(el,${JSON.stringify(value)});
    el.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  const tap = async (selector) => {
    const rect = await evaluate(
      `(() => { const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()`,
    );
    assert.ok(
      rect.x > 0 && rect.x < 390 && rect.y > 0 && rect.y < 844,
      `Tap target in viewport: ${selector}`,
    );
    await call("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x: rect.x, y: rect.y }],
    });
    await call("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  };
  const snapshot = async (name) => {
    await delay(220);
    await mkdir("qa/23", { recursive: true });
    const result = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    await writeFile(`qa/23/${name}.png`, Buffer.from(result.data, "base64"));
  };
  await viewport(390, 844);
  await call("Emulation.setTouchEmulationEnabled", { enabled: true });
  await call("Page.navigate", { url: "http://127.0.0.1:5173/donors/1" });
  await until("document.querySelector('.contact-log-action .button')");
  const today = await evaluate(
    `new Intl.DateTimeFormat('en-CA',{timeZone:'America/Phoenix'}).format(new Date())`,
  );
  // Exactly three real touch gestures from the donor detail page, with no typing/scrolling.
  await tap(".contact-log-action > .button");
  await until("document.querySelector('dialog[open]')");
  assert.equal(
    await evaluate("document.activeElement.tagName"),
    "H2",
    "Focus enters sheet without opening mobile keyboard",
  );
  assert.equal(
    await evaluate("document.querySelector('dialog[open] input[type=date]').value"),
    today,
  );
  await tap('input[value="call"]');
  await snapshot("mobile-contact");
  await tap("dialog[open] footer .button");
  await until(
    "!document.querySelector('dialog[open]') && document.querySelector('.save-notice').textContent.includes('Contact logged')",
  );
  assert.ok(
    await evaluate("document.querySelector('.relationship-timeline').textContent.includes('Call')"),
  );
  assert.ok(
    await evaluate(
      "document.querySelector('.giving-summary').textContent.includes('Last contacted')",
    ),
  );
  assert.equal(
    await evaluate("document.activeElement.textContent.trim()"),
    "Log contact",
    "Focus restores after save",
  );
  const logged = requests.find((r) => r.path.endsWith("/interactions"));
  assert.equal(logged.method, "POST");
  assert.equal(logged.body.kind, "call");
  assert.equal(logged.body.occurred_on, today);
  assert.equal(logged.body.summary, null);
  assert.equal(
    Object.entries(logged.headers).find(([name]) => name.toLowerCase() === "x-csrf-token")?.[1],
    "synthetic-csrf",
  );
  assert.ok(requests.filter((r) => r.path === "/donors/1").length >= 2);
  assert.ok(requests.filter((r) => r.path === "/donors/1/timeline").length >= 2);
  for (const kind of ["text", "email", "meeting", "note"]) {
    await clickText("Log contact");
    await evaluate(`document.querySelector('input[value=${kind}]').click()`);
    await clickText("Save contact");
    await until("!document.querySelector('dialog[open]')");
    assert.equal(requests.filter((r) => r.path.endsWith("/interactions")).at(-1).body.kind, kind);
  }
  // Keyboard: enter, radio navigation, focus containment, Escape, restoration, draft retention.
  await key("Enter", "Enter", 13);
  await until("document.querySelector('dialog[open]')");
  await key("Tab", "Tab", 9);
  assert.equal(await evaluate("document.activeElement.getAttribute('aria-label')"), "Close sheet");
  await key("Tab", "Tab", 9);
  await key("ArrowRight", "ArrowRight", 39);
  assert.equal(await evaluate("document.querySelector('input[value=text]').checked"), true);
  await fill("dialog[open] textarea", "Synthetic notes retained on failure.");
  await fill("dialog[open] input[type=date]", "2026-11-10");
  for (let i = 0; i < 12; i++) {
    await key("Tab", "Tab", 9);
    assert.equal(
      await evaluate("Boolean(document.activeElement.closest('dialog[open]'))"),
      true,
      "Native focus trap",
    );
  }
  await key("Escape", "Escape", 27);
  await until("!document.querySelector('dialog[open]')");
  await clickText("Log contact");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] textarea').value"),
    "Synthetic notes retained on failure.",
  );
  for (const status of [422, 400, 500, 501, 401, -1]) {
    failure = status;
    await clickText("Save contact");
    await until(
      "document.querySelector('dialog[open] [role=alert]') && !document.querySelector('dialog[open] button[type=button]').disabled",
    );
    assert.equal(
      await evaluate("document.querySelector('dialog[open] textarea').value"),
      "Synthetic notes retained on failure.",
    );
    assert.equal(
      await evaluate("document.querySelector('dialog[open] input[type=date]').value"),
      "2026-11-10",
    );
    assert.equal(await evaluate("document.querySelector('input[value=text]').checked"), true);
    assert.equal(await evaluate("document.querySelector('.save-notice').textContent"), "");
    await snapshot(status === 422 ? "mobile-validation" : "mobile-error");
  }
  failure = 0;
  waitMs = -1;
  const before = requests.filter((r) => r.path.endsWith("/interactions")).length;
  await clickText("Save contact");
  await until("document.querySelector('dialog[open] form').getAttribute('aria-busy')==='true'");
  await clickText("Saving contact…");
  await key("Escape", "Escape", 27);
  assert.equal(
    await evaluate("Boolean(document.querySelector('dialog[open]'))"),
    true,
    "Pending save cannot be dismissed",
  );
  releaseSave();
  await until("!document.querySelector('dialog[open]')");
  assert.equal(
    requests.filter((r) => r.path.endsWith("/interactions")).length,
    before + 1,
    "No duplicate pending writes",
  );
  waitMs = 0;
  // Create then replace, reload from server-shaped responses, complete the actual entity ID.
  await clickText("Set next step");
  await fill("dialog[open] input:not([type])", "Share the student showcase invitation");
  await fill("dialog[open] input[type=date]", "2026-11-20");
  failure = 422;
  await clickText("Save next step");
  await until("document.querySelector('dialog[open] [role=alert]')");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] input:not([type])').value"),
    "Share the student showcase invitation",
  );
  failure = 0;
  await clickText("Save next step");
  await until(
    "!document.querySelector('dialog[open]') && document.querySelector('.next-step-title').textContent.includes('Share')",
  );
  const firstId = activeStep.id;
  await clickText("Set a new next step");
  await fill("dialog[open] input:not([type])", "Follow up after the showcase");
  await fill("dialog[open] input[type=date]", "2026-11-24");
  await snapshot("mobile-next-step");
  await viewport(1440, 900);
  await snapshot("desktop-next-step");
  await viewport(390, 844);
  await clickText("Save next step");
  await until(
    "!document.querySelector('dialog[open]') && document.querySelector('.next-step-title').textContent.includes('Follow up')",
  );
  assert.notEqual(activeStep.id, firstId);
  await call("Page.reload");
  await delay(250);
  await until("document.querySelector('.next-step-actions .button:not(:disabled)')");
  assert.equal(
    await evaluate("document.querySelector('.next-step-title').textContent"),
    activeStep.title,
  );
  // Timeline failure gates completion and recovers independently.
  timelineFailure = true;
  await refresh();
  await until("document.querySelector('#relationship-timeline [role=alert]')");
  assert.equal(
    await evaluate("document.querySelector('.next-step-actions .button').disabled"),
    true,
  );
  timelineFailure = false;
  await clickText("Try again");
  await until("document.querySelector('.next-step-actions .button:not(:disabled)')");
  for (const status of [404, 409, 500, -1]) {
    failure = status;
    await clickText("Mark complete");
    await until("document.querySelector('.next-step-workspace [role=alert]')");
    await until("document.querySelector('.next-step-actions .button:not(:disabled)')");
    assert.equal(
      await evaluate("document.querySelector('.next-step-title').textContent"),
      activeStep.title,
    );
  }
  failure = 0;
  await clickText("Mark complete");
  await until("document.querySelector('.next-step-title').textContent==='No next step set'");
  assert.ok(
    requests.some((r) => r.path === `/next-steps/${activeStep.id}/done` && r.method === "POST"),
  );
  assert.ok(
    await evaluate(
      "document.querySelector('.relationship-timeline').textContent.includes('Completed next step: Follow up after the showcase')",
    ),
  );
  await snapshot("mobile-success");
  // Actual screenshots at all required widths; long donor name and zoom-equivalent layout.
  await evaluate("document.querySelector('.contact-log-action > .button').focus()");
  await clickText("Log contact");
  await evaluate("document.querySelector('input[value=meeting]').click()");
  for (const [width, height, name] of [
    [1440, 900, "desktop-contact"],
    [768, 1024, "tablet-contact"],
    [720, 450, "zoom-contact"],
    [390, 844, "mobile-contact-final"],
  ]) {
    await viewport(width, height);
    assert.equal(
      await evaluate(
        "document.documentElement.scrollWidth <= innerWidth && document.querySelector('dialog[open]').scrollWidth <= document.querySelector('dialog[open]').clientWidth",
      ),
      true,
      `No horizontal overflow at ${width}`,
    );
    await snapshot(name);
  }
  donor.display_name =
    "The Synthetic Southwestern Community Foundation for Technology and Creative Learning Partnerships";
  await refresh();
  assert.equal(
    await evaluate("document.querySelector('dialog[open]').scrollWidth <= innerWidth"),
    true,
  );
  await snapshot("mobile-long-name");
  await call("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('dialog[open]')).animationName"),
    "none",
  );
  await fill("dialog[open] textarea", "Private synthetic draft");
  failure = 403;
  await clickText("Save contact");
  await until("document.querySelector('dialog[open] [role=alert]')");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] textarea').value"),
    "Private synthetic draft",
  );
  assert.equal(
    await evaluate("document.querySelector('dialog[open] footer .button').disabled"),
    true,
  );
  await key("Escape", "Escape", 27);
  assert.equal(
    await evaluate("document.activeElement.id"),
    "main",
    "Focus returns to workspace when permission loss removes opener",
  );
  assert.equal(
    await evaluate("document.querySelector('.contact-log-action > .button')"),
    null,
    "403 hides contact action",
  );
  failure = 0;
  donor.contact_visible = false;
  donor.can_act = false;
  await refresh();
  assert.equal(await evaluate("document.querySelector('.next-step-actions')"), null);
  assert.equal(await evaluate("document.body.innerHTML.includes('alex@example.test')"), false);
  await snapshot("mobile-restricted");
  donor.contact_visible = true;
  donor.can_act = false;
  await refresh();
  assert.equal(
    await evaluate("document.querySelector('.next-step-actions')"),
    null,
    "can_act independently hides actions",
  );
  donor.can_act = true;
  donor.do_not_contact = true;
  await call("Page.reload");
  await delay(250);
  await until("document.querySelector('.contact-log-action > .button')");
  await clickText("Log contact");
  assert.ok(
    await evaluate(
      "document.querySelector('dialog[open]').textContent.includes('past contact or an internal note')",
    ),
  );
  await key("Escape", "Escape", 27);
  await clickText("Set next step");
  await fill("dialog[open] input:not([type])", "Internal stewardship review");
  failure = 403;
  await clickText("Save next step");
  await until("document.querySelector('dialog[open] [role=alert]')");
  assert.equal(
    await evaluate("document.querySelector('dialog[open] input:not([type])').value"),
    "Internal stewardship review",
  );
  await key("Escape", "Escape", 27);
  assert.equal(
    await evaluate("document.querySelector('.next-step-actions')"),
    null,
    "403 hides next-step actions",
  );
  assert.deepEqual(routeErrors, []);
  assert.deepEqual(errors, []);
  console.log(
    "PASS: three real taps, all contact kinds, CSRF/payloads, refresh, next-step create/replace/reload/complete, validation/network/permission errors, drafts, pending deduplication, keyboard/focus, responsive screenshots, reduced motion.",
  );
} finally {
  socket?.close();
  browser.kill();
}
