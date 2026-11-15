// Start Vite, then run: node tests/directory.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9339;
const profile = resolve(".test-build/directory-browser");
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
  if (process.env.DIRECTORY_LIVE_URL) {
    // Optional integration pass against a local backend seeded with synthetic QA users.
    // Credentials come from the caller and never enter source, logs, or screenshots.
    const base = new URL(process.env.DIRECTORY_LIVE_URL);
    assert.ok(["127.0.0.1", "localhost"].includes(base.hostname), "Live QA is local only");
    assert.ok(process.env.DIRECTORY_QA_EMAIL && process.env.DIRECTORY_QA_PASSWORD);
    await call("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await call("Page.navigate", { url: new URL("/login", base).href });
    await until("document.querySelector('#email')");
    await evaluate("document.querySelector('#email').focus()");
    await call("Input.insertText", { text: process.env.DIRECTORY_QA_EMAIL });
    await evaluate("document.querySelector('#password').focus()");
    await call("Input.insertText", { text: process.env.DIRECTORY_QA_PASSWORD });
    await key("Enter", "Enter", 13);
    await until("location.pathname === '/'");
    await call("Page.navigate", { url: new URL("/donors", base).href });
    await until("document.querySelectorAll('.relationship-row').length === 1");
    assert.ok(
      await evaluate(
        "document.querySelector('.relationship-row').textContent.includes('Synthetic Alex Rivera')",
      ),
    );
    await clickText("All donors");
    await until(
      "[...document.querySelectorAll('.relationship-row')].some(row => row.textContent.includes('Synthetic Samira Brooks'))",
    );
    await evaluate("document.querySelector('#donor-search').focus()");
    await call("Input.insertText", { text: "Synthetic Samira" });
    await key("Enter", "Enter", 13);
    await until(
      "document.querySelectorAll('.relationship-row').length === 1 && document.querySelector('.relationship-row').textContent.includes('Synthetic Samira')",
    );
    const privacy = await evaluate(`(async () => {
      const page = await (await fetch('/api/app/donors?scope=all&q=Synthetic%20Samira')).json();
      const donor = await (await fetch('/api/app/donors/' + page.items[0].id)).json();
      return donor.contact_visible === false && donor.email === null && donor.phone === null && donor.can_act === false && donor.contact_via === 'Synthetic Avery Chen';
    })()`);
    assert.equal(privacy, true, "Real API masks another owner's contact information");
    await evaluate("document.querySelector('.relationship-row summary').focus()");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.relationship-row details').open");
    assert.ok(
      await evaluate("document.querySelector('.gift-preview').textContent.includes('$1,250.00')"),
    );
    await delay(250);
    const shot = await call("Page.captureScreenshot", { format: "png" });
    await mkdir("qa/19", { recursive: true });
    await writeFile("qa/19/live-local.png", Buffer.from(shot.data, "base64"));
    assert.deepEqual(errors, []);
    console.log(
      "PASS: real FastAPI + isolated local PostgreSQL; UI login, My/All, server search, gift expansion, and non-owner contact masking. Synthetic seed data only; no mocked APIs.",
    );
  } else {
    await call("Page.addScriptToEvaluateOnNewDocument", {
      source: `
    window.directoryQA = { mode: 'normal', requests: [], delay: 0, optionsReady: false };
    const nativeFetch = window.fetch.bind(window);
    const owners = [
      { id: 1, display_name: 'Morgan Ellis', is_active: true },
      { id: 2, display_name: 'Avery Chen', is_active: true },
      { id: 3, display_name: 'Jordan Vale', is_active: false },
    ];
    const names = ['Alex Rivera', 'Desert Learning Foundation', 'Samira Brooks', 'Northstar Community Partners', 'Elliot Quinn', 'Remy Park'];
    const donors = Array.from({length: 205}, (_, i) => ({
      id: i + 1, display_name: i < 6 ? names[i] : 'Synthetic Supporter ' + String(i + 1).padStart(3, '0'),
      kind: i === 1 ? 'funder' : i === 3 ? 'organization' : 'person',
      organization: i === 0 ? 'Juniper Studio' : i === 3 ? 'Community education' : null,
      owner: owners[i % 3], total_12m_cents: 125000 + i * 2500, total_lifetime_cents: 310000 + i * 5000,
      last_gift_date: '2026-10-20', last_contact_date: i % 4 === 0 ? null : '2026-10-26',
      next_step_title: i % 3 === 0 ? 'Share the fall program update' : null,
      next_step_due: i % 3 === 0 ? '2026-11-19' : null,
      statuses: i === 0 ? ['new'] : i % 3 === 2 ? ['owner_inactive'] : i === 4 ? ['do_not_contact'] : i === 3 ? ['lapsed'] : [],
      recent_gifts: i === 4 ? [] : [{
        id: i + 1, donor_id: i + 1, donor_name: names[i % 6], attribution: 'linked', source: 'benevity',
        gross_cents: 25000, net_cents: 25000, fee_cents: 0, gift_date: '2026-10-20',
        program: 'AI Academy', is_matching_gift: i % 2 === 0, payer_name: 'Synthetic Company', assumed_thanked: false,
      }],
    }));
    window.fetch = async (input, options = {}) => {
      const url = new URL(String(input), location.origin);
      if (!url.pathname.startsWith('/api/app')) return nativeFetch(input, options);
      const qa = window.directoryQA;
      qa.requests.push(url.pathname + url.search);
      const reply = (body, status = 200) => new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
      if (url.pathname.endsWith('/auth/me')) return reply({id: 1, display_name: 'Morgan Ellis', email: 'morgan@example.test', is_super_admin: false, governance: {mode: 'flat', reassign_scope: 'anyone'}});
      if (url.pathname.endsWith('/members')) return qa.optionsReady ? reply({items: owners}) : reply({error:{message:'Member directory unavailable'}},501);
      if (url.pathname.endsWith('/programs')) return qa.optionsReady ? reply({items:[{id:5,name:'AI Academy',slug:'ai-academy',is_active:true}]}) : reply({error:{message:'Programs unavailable'}},501);
      if (url.pathname.endsWith('/donors')) {
        if (qa.delay) await new Promise((ok, fail) => {
          const timer = setTimeout(ok, qa.delay);
          options.signal?.addEventListener('abort', () => {clearTimeout(timer); fail(new DOMException('Aborted', 'AbortError'));}, {once:true});
        });
        if (qa.mode.startsWith('error')) return reply({error:{message:'Synthetic request failure'}}, Number(qa.mode.slice(5)));
        let items = qa.mode === 'empty' ? [] : donors;
        if (qa.mode === 'long') items = [{...donors[0], display_name:'The Synthetic Southwestern Community Foundation for Technology and Creative Learning Partnerships'}];
        if (qa.mode === 'one') items = donors.slice(0,1);
        if (url.searchParams.get('scope') === 'mine') items = items.filter(d => d.owner.id === 1);
        if (url.searchParams.get('q')) items = items.filter(d => d.display_name.toLowerCase().includes(url.searchParams.get('q').toLowerCase()));
        if (url.searchParams.get('owner')) items = items.filter(d => d.owner.id === Number(url.searchParams.get('owner')));
        if (url.searchParams.get('status')) items = items.filter(d => d.statuses.includes(url.searchParams.get('status')));
        const page = Number(url.searchParams.get('page') || 1);
        return reply({items:items.slice((page-1)*20,page*20),total:items.length,page,page_size:20});
      }
      return reply({error:{message:'No synthetic handler'}},501);
    };
  `,
    });
    const viewport = (width, height) =>
      call("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile: false,
      });
    const navigate = async () => {
      await call("Page.navigate", { url: process.env.APP_URL ?? "http://127.0.0.1:5173/donors" });
      await until("document.querySelectorAll('.relationship-row').length === 20");
    };
    await viewport(1440, 900);
    await navigate();
    assert.equal(
      await evaluate(
        "document.querySelector('[aria-label=\"Donor scope\"] button').getAttribute('aria-pressed')",
      ),
      "true",
    );
    assert.equal(
      await evaluate("document.querySelector('.directory-count').textContent.trim()"),
      "69 relationships in your care",
    );
    assert.equal(await evaluate("document.querySelectorAll('a[aria-current=page]').length"), 1);
    await evaluate("document.querySelector('.filter-disclosure > summary').focus()");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.filter-disclosure').open");
    await until(
      "document.querySelector('.filter-note')?.textContent.includes('Program filtering is currently unavailable')",
    );
    await evaluate("document.querySelector('.relationship-row summary').focus()");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.relationship-row details').open");
    assert.equal(
      await evaluate(
        "document.querySelector('.relationship-row .gift-preview').textContent.includes('Employer match')",
      ),
      true,
    );
    await key("Enter", "Enter", 13);
    await evaluate("document.querySelector('[aria-label=\"Donor scope\"] button').focus()");
    await key("Tab", "Tab", 9);
    assert.equal(await evaluate("document.activeElement.textContent.trim()"), "All donors");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.directory-count').textContent.includes('205')");
    await evaluate("document.querySelector('[aria-label=\"Next donor page\"]').focus()");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.pagination')?.textContent.includes('Page 2 of 11')");
    await evaluate("document.querySelector('#donor-search').focus()");
    await call("Input.insertText", { text: "Alex" });
    await key("Enter", "Enter", 13);
    await until("document.querySelectorAll('.relationship-row').length === 1");
    assert.ok(await evaluate("window.directoryQA.requests.at(-1).includes('q=Alex')"));
    assert.equal(await evaluate("location.search"), "", "Search stays out of URLs");
    assert.equal(
      await evaluate("document.querySelector('.pagination').textContent.includes('Page 1 of 1')"),
      true,
    );
    await clickText("Clear filters");
    await until("document.querySelectorAll('.relationship-row').length === 20");
    await evaluate("window.directoryQA.optionsReady = true");
    await clickText("Retry filters");
    await until("!document.querySelectorAll('.filter-fields select')[2].disabled");
    await evaluate(
      "const owner = document.querySelectorAll('.filter-fields select')[0]; owner.value='2'; owner.dispatchEvent(new Event('change',{bubbles:true}))",
    );
    await until("window.directoryQA.requests.at(-1).includes('owner=2')");
    await until("document.querySelector('.directory-count').textContent.includes('68')");
    await evaluate(
      "const status = document.querySelectorAll('.filter-fields select')[1]; status.value='owner_inactive'; status.dispatchEvent(new Event('change',{bubbles:true}))",
    );
    await until(
      "document.querySelector('.workspace-state h2')?.textContent === 'No matching relationships'",
    );
    await clickText("Clear filters");
    await until("document.querySelectorAll('.relationship-row').length === 20");
    const reloadMode = async (mode, scope = "mine") => {
      await evaluate(`window.directoryQA.mode = ${JSON.stringify(mode)}`);
      await clickText(scope === "mine" ? "My donors" : "All donors");
      await evaluate("window.dispatchEvent(new Event('focus'))");
    };
    // Switch scope to guarantee a fresh request; every filter change also proves page reset.
    for (const status of [401, 403, 409, 422, 500, 501]) {
      const wasMine = await evaluate(
        "document.querySelector('[aria-label=\"Donor scope\"] button').getAttribute('aria-pressed') === 'true'",
      );
      await reloadMode(`error${status}`, wasMine ? "all" : "mine");
      await until("document.querySelector('[role=alert]')");
      assert.equal(await evaluate("document.querySelectorAll('.relationship-row').length"), 0);
      await evaluate("window.directoryQA.mode = 'normal'");
      if (status === 401) {
        await clickText(wasMine ? "My donors" : "All donors");
      } else await clickText("Try again");
      await until("document.querySelectorAll('.relationship-row').length === 20");
    }
    await clickText("All donors");
    await until("document.querySelectorAll('.relationship-row').length === 20");
    await reloadMode("empty", "mine");
    await until(
      "document.querySelector('.workspace-state h2')?.textContent === 'Your relationship ledger starts here'",
    );
    await clickText("View all donors");
    await until(
      "document.querySelector('.workspace-state h2')?.textContent === 'No relationships recorded yet'",
    );
    await evaluate("window.directoryQA.mode = 'normal'; window.directoryQA.delay = 800");
    await clickText("My donors");
    await evaluate("document.querySelector('#donor-search').focus()");
    await call("Input.insertText", { text: "Synthetic" });
    await key("Enter", "Enter", 13);
    await until("document.querySelector('[aria-label=\"Loading relationships\"]')");
    await until("document.querySelectorAll('.relationship-row').length === 20");
    await evaluate("window.directoryQA.delay = 0");

    const screenshot = async (name) => {
      await evaluate("document.activeElement?.blur(); window.scrollTo(0,0)");
      await delay(250); // Capture settled state after the interface's 160 ms transitions.
      const shot = await call("Page.captureScreenshot", { format: "png" });
      await mkdir("qa/19", { recursive: true });
      await writeFile(`qa/19/${name}.png`, Buffer.from(shot.data, "base64"));
    };
    await navigate();
    await clickText("All donors");
    await until("document.querySelector('.directory-count').textContent.includes('205')");
    await screenshot("desktop");
    await evaluate("document.querySelector('.relationship-row summary').focus()");
    await key("Enter", "Enter", 13);
    await until("document.querySelector('.relationship-row details').open");
    await screenshot("desktop-gifts");
    for (const [width, height] of [
      [768, 1024],
      [390, 844],
    ]) {
      await viewport(width, height);
      await navigate();
      assert.equal(
        await evaluate("document.documentElement.scrollWidth <= innerWidth"),
        true,
        `No horizontal overflow at ${width}`,
      );
      if (width === 390) {
        assert.equal(await evaluate("document.querySelector('.filter-disclosure').open"), false);
        await evaluate("document.querySelector('.mobile-menu-button').focus()");
        await key("Enter", "Enter", 13);
        assert.equal(
          await evaluate(
            "document.querySelector('.mobile-menu-button').getAttribute('aria-expanded')",
          ),
          "true",
        );
        await evaluate("document.querySelector('#main-navigation a').focus()");
        await key("Escape", "Escape", 27);
        assert.equal(
          await evaluate("document.activeElement.classList.contains('mobile-menu-button')"),
          true,
        );
        assert.equal(
          await evaluate(
            "document.querySelector('.mobile-menu-button').getAttribute('aria-expanded')",
          ),
          "false",
        );
        await evaluate("document.querySelector('.relationship-row summary').focus()");
        await key("Enter", "Enter", 13);
        assert.equal(
          await evaluate("document.querySelector('.relationship-row details').open"),
          true,
        );
        await key("Enter", "Enter", 13);
        await screenshot("mobile");
      } else await screenshot("tablet");
    }
    await evaluate("window.directoryQA.mode = 'long'");
    await clickText("All donors");
    await until("document.querySelectorAll('.relationship-row').length === 1");
    assert.equal(
      await evaluate("document.documentElement.scrollWidth <= innerWidth"),
      true,
      "Long names wrap",
    );
    await screenshot("mobile-long-name");
    await viewport(720, 450); // 1440x900 at 200% page zoom has a 720x450 CSS viewport.
    await call("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    assert.equal(
      await evaluate("getComputedStyle(document.querySelector('summary')).transitionDuration"),
      "0s",
    );
    assert.equal(
      await evaluate("document.documentElement.scrollWidth <= innerWidth"),
      true,
      "200% layout fits",
    );
    assert.deepEqual(errors, [], "No uncaught application errors");
    console.log(
      "PASS: scope, 205-record pagination, keyboard disclosure/navigation/search, filter requests and reset, empty states, 401/403/409/422/500/501 recovery, slow loading, mobile menu, long names, 390/768/1440 layouts, 200% layout, reduced motion. Synthetic API responses only.",
    );
  }
} finally {
  socket?.close();
  browser.kill();
}
