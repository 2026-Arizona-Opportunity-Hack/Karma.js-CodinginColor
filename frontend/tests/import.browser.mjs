// Start Vite, then run: node tests/detail.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9342;
const profile = resolve(".test-build/import-browser");
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
  const empty = { count: 0, cents: 0, gift_count: 0, donation_cents: 0, match_cents: 0 };
  const cls = (count, gift_count, donation_cents, match_cents = 0) => ({
    count,
    gift_count,
    donation_cents,
    match_cents,
    cents: donation_cents + match_cents,
  });
  const summary = {
    rows_read: 5,
    gift_count: 6,
    total_cents: 80000,
    donation_cents: 55000,
    match_cents: 25000,
    new_gifts: cls(2, 4, 30000, 25000),
    already_imported: cls(1, 1, 10000),
    needs_review: cls(1, 1, 15000),
    invalid: cls(1, 0, 0),
    anonymous: cls(1, 1, 10000),
    donor_updates: empty,
    updated_count: 0,
    new_donors: 1,
    donors_matched: 1,
    unmapped_campaigns: ["Synthetic campaign"],
    rows_reconcile: true,
    cents_reconcile: true,
    reconciles: true,
  };
  const owner = { id: 1, display_name: "Jordan QA (synthetic)", is_active: true };
  const batch = {
    id: 22,
    source: "benevity",
    filename: "synthetic-import.csv",
    status: "previewed",
    uploaded_by: owner,
    created_at: "2026-11-15T08:00:00Z",
    summary,
  };
  const preview = {
    batch,
    summary,
    commit_allowed: true,
    updates: [],
    invalid_rows: [{ row_number: 6, reason: "invalid_date: 31/31/2025" }],
  };
  const initialReviews = [1, 2, 3].map((id) => ({
    id,
    status: "open",
    file: "synthetic-import.csv",
    row_number: id + 1,
    incoming: {
      display_name: "Alex Morgan (synthetic)",
      organization: "Community Learning Collective",
      email: "alex@example.test",
      phone: "+16025550123",
    },
    candidates: [
      {
        donor_id: 7,
        display_name: "Alexandra Morgan (synthetic)",
        owner,
        match_reason: "email_name_conflict",
      },
    ],
  }));
  const gift = (id, source, attribution = "anonymous") => ({
    id,
    source,
    attribution,
    gross_cents: 10000,
    fee_cents: 0,
    net_cents: 10000,
    donor_id: null,
    donor_name: null,
    gift_date: "2026-11-14",
    program: "General",
    is_matching_gift: false,
  });
  let reviewItems = structuredClone(initialReviews);
  let giftItems = [gift(1, "benevity"), gift(2, "generic"), gift(3, "zeffy", "pending_review")];
  let statusFailure = 0;
  let failure = 0,
    uploadFailure = 0,
    commitCount = 0,
    saved = false,
    lostResponse = false;
  const writes = [];
  const routeErrors = [];
  const reply = (requestId, body, status = 200) =>
    call("Fetch.fulfillRequest", {
      requestId,
      responseCode: status,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(JSON.stringify(body)).toString("base64"),
    });
  const handle = async ({ requestId, request }) => {
    const url = new URL(request.url);
    const path = url.pathname.replace("/api/app", "");
    if (request.method !== "GET") {
      writes.push({ path, body: request.postData, headers: request.headers });
      await delay(180);
      const fail = path === "/imports/preview" ? uploadFailure : failure;
      if (fail)
        return reply(requestId, { error: { message: `Synthetic backend failure ${fail}` } }, fail);
    }
    if (path === "/auth/me")
      return reply(requestId, {
        ...owner,
        email: "qa@example.test",
        is_super_admin: false,
        governance: { mode: "flat", reassign_scope: "anyone" },
      });
    if (path === "/imports/preview") {
      saved = false;
      return reply(requestId, preview);
    }
    if (path === "/imports/22/commit") {
      commitCount++;
      saved = true;
      if (lostResponse)
        return call("Fetch.failRequest", { requestId, errorReason: "InternetDisconnected" });
      return reply(requestId, { ...batch, status: "committed" });
    }
    if (path === "/imports/22" && statusFailure)
      return reply(
        requestId,
        { error: { message: "Preview expired or unavailable. Upload the file again." } },
        statusFailure,
      );
    if (path === "/imports/22")
      return reply(requestId, { ...batch, status: saved ? "committed" : "previewed" });
    if (path === "/imports")
      return reply(requestId, { items: saved ? [{ ...batch, status: "committed" }] : [] });
    if (path === "/reviews")
      return reply(requestId, {
        items: reviewItems.filter((r) =>
          url.searchParams.get("status") === "decided" ? r.status !== "open" : r.status === "open",
        ),
      });
    if (path.match(/reviews\/\d+\/decide/)) {
      const id = Number(path.split("/")[2]);
      const body = JSON.parse(request.postData);
      const review = reviewItems.find((r) => r.id === id);
      review.status = { link: "linked", create_new: "created_new", anonymous: "anonymous" }[
        body.decision
      ];
      return reply(requestId, review);
    }
    if (path === "/gifts/unattributed") return reply(requestId, { items: giftItems });
    if (path === "/donors")
      return reply(requestId, {
        items: [{ id: 7, display_name: "Alexandra Morgan (synthetic)" }],
        total: 1,
        page: 1,
        page_size: 20,
      });
    if (path === "/gifts/2/attribute") {
      giftItems = giftItems.filter((g) => g.id !== 2);
      return reply(requestId, { ...gift(2, "generic", "linked"), donor_id: 7 });
    }
    return reply(requestId, { error: { message: `Unexpected ${path}` } }, 404);
  };
  const handler = socket.onmessage;
  socket.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === "Fetch.requestPaused")
      handle(msg.params).catch((e) => {
        // TanStack Query cancels obsolete GETs when a test navigates away.
        if (!(msg.params.request.method === "GET" && e.message.includes("Invalid InterceptionId")))
          routeErrors.push(e);
      });
    handler(event);
  };
  await call("Fetch.enable", { patterns: [{ urlPattern: "*/api/app/*" }] });
  await call("Network.setCookie", {
    name: "cic_csrf",
    value: "synthetic-csrf",
    url: "http://127.0.0.1:5173",
  });
  for (const width of [390, 768, 1440]) {
    await size(width);
    await open();
    await chooseFile();
    await clickText("Preview file");
    await until("document.querySelector('.reconciliation-table')");
    assert.ok(
      (await evaluate("document.querySelector('.invalid-rows').textContent")).includes(
        "invalid_date: 31/31/2025",
      ),
    );
    assert.deepEqual(
      await evaluate(
        "[...document.querySelectorAll('.import-metrics strong')].map(e=>e.textContent)",
      ),
      ["5", "6", "$800.00"],
    );
    await widthOK();
    await evaluate("document.querySelector('.import-file-heading').scrollIntoView()");
    await shot(`${width}-preview`);
    await clickText("Review & confirm");
    await until("document.querySelector('dialog[open]')");
    assert.equal(await evaluate("document.activeElement.tagName"), "H2");
    await key("Tab", "Tab", 9);
    await key("Escape", "Escape", 27);
    await until("!document.querySelector('dialog[open]')");
    await clickText("Review & confirm");
    await shot(`${width}-confirm`);
    const before = commitCount;
    await evaluate(
      "[...document.querySelectorAll('dialog[open] button')].find(b=>b.textContent==='Confirm import').click(); [...document.querySelectorAll('dialog[open] button')].find(b=>b.textContent==='Confirm import').click()",
    );
    await until("document.querySelector('.import-success')");
    assert.equal(commitCount, before + 1, "One request despite repeated click");
    await widthOK();
    await shot(`${width}-success`);
  }
  for (const code of [400, 401, 403, 409, 413, 415, 422, 500, 501]) {
    await open();
    await chooseFile();
    uploadFailure = code;
    await clickText("Preview file");
    await until("document.querySelector('[role=alert]')");
    assert.ok(
      (await evaluate("document.body.textContent")).includes(`Synthetic backend failure ${code}`),
    );
    assert.equal(await evaluate("!!document.querySelector('.reconciliation-table')"), false);
    uploadFailure = 0;
  }
  for (const code of [400, 401, 403, 404, 409, 422, 500, 501]) {
    await open();
    await chooseFile();
    await clickText("Preview file");
    await until("document.querySelector('.reconciliation-table')");
    failure = code;
    await clickText("Review & confirm");
    await clickText("Confirm import");
    await until("document.querySelector('dialog[open] [role=alert]')");
    assert.equal(
      await evaluate("!!document.querySelector('.import-success')"),
      false,
      "No false success",
    );
    await clickText("Back to preview");
    await clickText("Check import status");
    await until(
      "[...document.querySelectorAll('button')].some(b=>b.textContent==='Review & confirm') && ![...document.querySelectorAll('button')].some(b=>b.textContent==='Checking - ')",
    );
    if (code === 409)
      assert.equal(
        await evaluate(
          "[...document.querySelectorAll('button')].find(b=>b.textContent==='Review & confirm').disabled",
        ),
        true,
      );
    failure = 0;
  }
  // Expired/evicted preview: do not leave a reusable commit action.
  await open();
  await chooseFile();
  await clickText("Preview file");
  await until("document.querySelector('.reconciliation-table')");
  failure = 404;
  statusFailure = 404;
  await clickText("Review & confirm");
  await clickText("Confirm import");
  await until("document.querySelector('dialog[open] [role=alert]')");
  await clickText("Back to preview");
  await clickText("Check import status");
  await until("document.body.textContent.includes('This preview cannot safely be reused')");
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('button')].find(b=>b.textContent==='Review & confirm').disabled",
    ),
    true,
  );
  failure = 0;
  statusFailure = 0;
  const originalAllowed = preview.commit_allowed;
  preview.commit_allowed = false;
  await open();
  await chooseFile();
  await clickText("Preview file");
  await until("document.querySelector('.reconciliation-table')");
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('button')].find(b=>b.textContent==='Review & confirm').disabled",
    ),
    true,
  );
  preview.commit_allowed = originalAllowed;
  // Lost success response: status lookup recovers, with no second POST.
  await open();
  await chooseFile();
  await clickText("Preview file");
  await until("document.querySelector('.reconciliation-table')");
  lostResponse = true;
  await clickText("Review & confirm");
  await clickText("Confirm import");
  await until("document.querySelector('dialog[open] [role=alert]')");
  const beforeRecovery = commitCount;
  await clickText("Back to preview");
  await clickText("Check import status");
  await until("document.querySelector('.import-success')");
  assert.equal(commitCount, beforeRecovery);
  lostResponse = false;
  // Spreadsheet rows are donor updates, with zero gifts. No unchecked field is sent.
  preview.updates = [
    {
      donor_id: 7,
      donor_name: "Alexandra Morgan (synthetic)",
      changes: { email: { old_hidden: true, new_value: "new@example.test" } },
    },
  ];
  preview.summary = {
    ...summary,
    rows_read: 2,
    gift_count: 0,
    total_cents: 0,
    donation_cents: 0,
    match_cents: 0,
    new_gifts: empty,
    already_imported: empty,
    needs_review: empty,
    invalid: empty,
    anonymous: empty,
    donor_updates: cls(2, 0, 0),
    updated_count: 1,
  };
  preview.invalid_rows = [];
  await open();
  await chooseFile();
  await clickText("Preview file");
  await until("document.querySelector('.reconciliation-table')");
  assert.equal(
    await evaluate("document.querySelectorAll('.import-metrics strong')[1].textContent"),
    "0",
  );
  await clickText("Review donor updates");
  await until("document.querySelector('dialog[open] input[type=checkbox]')");
  assert.equal(await evaluate("document.querySelectorAll('dialog input:checked').length"), 0);
  await key(" ", "Space", 32);
  assert.equal(await evaluate("document.querySelectorAll('dialog input:checked').length"), 1);
  await clickText("Review import confirmation");
  await clickText("Confirm import");
  await until("document.querySelector('.import-success')");
  assert.deepEqual(JSON.parse(writes.filter((w) => w.path.endsWith("/commit")).at(-1).body), {
    approved_updates: [{ donor_id: 7, fields: ["email"] }],
  });
  // Separate identity review, three explicit decisions, persisted only after confirmation.
  for (const width of [390, 768, 1440]) {
    await size(width);
    await open("/review");
    await until("document.querySelector('.review-card')");
    await widthOK();
    await evaluate("document.querySelector('.review-card').scrollIntoView()");
    await shot(`${width}-comparison`);
    await evaluate(
      "document.querySelector('.identity-comparison > section + section').scrollIntoView()",
    );
    await shot(`${width}-candidates`);
    await evaluate("document.querySelector('.review-decision').scrollIntoView({block:'center'})");
    await shot(`${width}-decision`);
  }
  for (const [index, value] of ["link:7", "create_new", "anonymous"].entries()) {
    await select(".review-decision select", value);
    await evaluate("document.querySelector('.review-decision button').click()");
    await until("document.querySelector('dialog[open]')");
    const before = writes.length;
    await clickText("Save decision");
    await until("!document.querySelector('dialog[open]')");
    assert.equal(writes.length, before + 1);
    assert.deepEqual(
      JSON.parse(writes.at(-1).body),
      index === 0 ? { decision: "link", donor_id: 7 } : { decision: value },
    );
  }
  await until("document.body.textContent.includes('The review desk is clear')");
  reviewItems = structuredClone(initialReviews);
  await clickText("Refresh records");
  await until("document.querySelector('.review-card')");
  failure = 409;
  await select(".review-decision select", "link:7");
  await evaluate("document.querySelector('.review-decision button').click()");
  await clickText("Save decision");
  await until("document.querySelector('dialog[open] [role=alert]')");
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('dialog button')].some(b=>b.textContent==='Save decision')",
    ),
    false,
  );
  failure = 0;
  await clickText("Reload before retrying");
  await until("!document.querySelector('dialog[open]')");
  await clickText("Unattributed gifts");
  await until("document.querySelectorAll('.gift-review').length===3");
  assert.equal(
    await evaluate(
      "document.querySelector('.gift-review').querySelectorAll('button,input,select').length",
    ),
    0,
    "Benevity opt-out offers no attachment controls",
  );
  assert.equal(
    await evaluate(
      "document.querySelectorAll('.gift-review')[2].querySelectorAll('button,input,select').length",
    ),
    0,
    "Pending-review gift uses review queue",
  );
  await size(390);
  await widthOK();
  await shot("390-attribution");
  await select(".gift-match input", "Alex");
  await clickText("Search donors");
  await until("document.querySelector('.gift-match select')");
  await select(".gift-match select", "7");
  await clickText("Attach to Donor");
  await clickText("Save decision");
  await until("document.querySelectorAll('.gift-review').length===2");
  assert.deepEqual(JSON.parse(writes.at(-1).body), { donor_id: 7 });
  assert.ok(
    writes.every((w) =>
      Object.entries(w.headers).some(
        ([k, v]) => k.toLowerCase() === "x-csrf-token" && v === "synthetic-csrf",
      ),
    ),
    "Actual API client sends CSRF on every write",
  );
  // Density, long identities and a small-height layout equivalent to 200% zoom.
  await size(720, 450);
  await call("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  for (const count of [0, 1, 20, 200]) {
    reviewItems = Array.from({ length: count }, (_, i) => ({
      ...structuredClone(initialReviews[0]),
      id: 1000 + i,
      incoming: {
        ...initialReviews[0].incoming,
        display_name: "Synthetic community learning partner ".repeat(6),
      },
      candidates: initialReviews[0].candidates,
    }));
    await open("/review");
    await until(`document.querySelectorAll('.review-card').length === ${count}`);
    await widthOK();
  }
  assert.equal(await evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"), true);
  assert.deepEqual(routeErrors, []);
  assert.deepEqual(errors, []);
  console.log(
    "PASS: upload ? preview ? confirmation ? commit, three viewports, invalid reasons, row/gift accounting, field approvals, duplicate decisions, status/permission failures, repeat prevention, lost-response recovery, CSRF, Benevity opt-out and generic attachment.",
  );
} finally {
  socket?.close();
  browser.kill();
}
