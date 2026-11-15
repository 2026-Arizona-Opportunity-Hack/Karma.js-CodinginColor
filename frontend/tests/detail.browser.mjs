// Start Vite, then run: node tests/detail.browser.mjs
// All API responses below are synthetic and exist only inside this isolated browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = 9340;
const profile = resolve(".test-build/detail-browser");
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
  await call("Page.addScriptToEvaluateOnNewDocument", {
    source: `
    const owner = {id:1,display_name:'Jordan Lee',is_active:true};
    const gift = {id:1,donor_id:1,donor_name:'Alex Rivera',gift_date:'2026-11-12',gross_cents:125000,fee_cents:0,net_cents:125000,program:'Creative Coding',source:'benevity',attribution:'linked',is_matching_gift:false,assumed_thanked:false};
    const donor = {id:1,kind:'person',display_name:'Alex Rivera',organization:'Community Learning Collective',created_at:'2026-01-10T17:00:00Z',owner,contact_visible:true,can_act:true,can_reassign:false,email:'alex@example.test',phone:'+1 602 555 0100',notes:'Interested in supporting the next student showcase.',contact_via:null,do_not_contact:false,statuses:['new'],total_12m_cents:250000,total_lifetime_cents:575000,last_gift_date:'2026-11-12',last_contact_date:'2026-11-13',next_step_title:'Share the student showcase invitation',next_step_due:'2026-11-20',recent_gifts:[gift,{...gift,id:2,is_matching_gift:true,payer_name:'Demo Employer',gross_cents:50000}]};
    const events = [
      {kind:'gift',entity_id:1,at:'2026-11-12T19:00:00Z',title:'Gift to Creative Coding',detail:'Benevity · Donation',amount_cents:125000},
      {kind:'contact',entity_id:2,at:'2026-11-13T19:00:00Z',title:'Meeting',detail:'Discussed the upcoming student showcase.',by:'Jordan Lee'},
      {kind:'next_step',entity_id:3,at:'2026-11-14T19:00:00Z',title:'Share the student showcase invitation',by:'Jordan Lee'},
      {kind:'owner_change',entity_id:4,at:'2026-01-10T19:00:00Z',title:'Assigned to Jordan Lee',by:'Demo Admin'},
      {kind:'note',entity_id:5,at:'2026-11-10T19:00:00Z',title:'Stewardship note',detail:'Demo note',by:'Jordan Lee'},
      {kind:'message',entity_id:6,at:'2026-11-11T19:00:00Z',title:'Thank-you sent',by:'Jordan Lee'},
    ];
    window.detailQA = {donor,events,initialEvents:events,mode:'normal',timelineStatus:200,detailStatus:200,delay:Number(sessionStorage.getItem('detail-delay') || 0),requests:[]};
    window.fetch = async (input, options={}) => {
      const q = window.detailQA;
      const path = new URL(input,location.origin).pathname;
      q.requests.push(path);
      const reply = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
      if(path.endsWith('/auth/me')) return reply({...owner,email:'jordan@example.test',is_super_admin:false,governance:{mode:'flat',reassign_scope:'own_only'}});
      if(q.delay) await new Promise(resolve => setTimeout(resolve,q.delay));
      if(path.endsWith('/timeline')) return q.timelineStatus === 200 ? reply({items:q.events}) : reply({error:{message:'Synthetic timeline failure'}},q.timelineStatus);
      if(/\\/donors\\/\\d+$/.test(path)) return q.detailStatus === 200 ? reply(q.donor) : reply({error:{message:'Synthetic detail failure'}},q.detailStatus);
      if(path.endsWith('/donors')) return reply({items:[q.donor],total:1,page:1,page_size:20});
      return reply({error:{message:'Not implemented'}},501);
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
  const navigate = async (path = "/donors/1") => {
    await call("Page.navigate", { url: `http://127.0.0.1:5173${path}` });
    await until(
      path === "/donors"
        ? "document.querySelector('.relationship-row')"
        : "document.querySelector('.relationship-timeline')",
    );
  };
  const refresh = async () => {
    await evaluate("window.dispatchEvent(new Event('visibilitychange'))");
  };
  const snapshot = async (name) => {
    await evaluate("document.activeElement?.blur(); window.scrollTo(0,0)");
    await delay(200);
    const shot = await call("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: name !== "mobile-dense-long-name",
    });
    await mkdir("qa/20", { recursive: true });
    await writeFile(`qa/20/${name}.png`, Buffer.from(shot.data, "base64"));
  };
  await viewport(1440, 900);
  await navigate();
  assert.equal(
    await evaluate("document.querySelector('.trail-event h3').textContent"),
    "Share the student showcase invitation",
  );
  assert.equal(await evaluate("document.querySelectorAll('.trail-event').length"), 6);
  assert.equal(await evaluate("document.querySelectorAll('a[href^=mailto]').length"), 1);
  assert.equal(await evaluate("document.querySelectorAll('a[aria-current=page]').length"), 1);
  await snapshot("desktop");
  // Native keyboard navigation into the signature module, with a visible focus ring.
  await key("Tab", "Tab", 9);
  await evaluate("document.querySelector('a[href=\"#relationship-timeline\"]').focus()");
  assert.notEqual(await evaluate("getComputedStyle(document.activeElement).outlineStyle"), "none");
  await key("Enter", "Enter", 13);
  await until("document.activeElement.id === 'relationship-timeline'");
  for (const [width, height, name] of [
    [768, 1024, "tablet"],
    [390, 844, "mobile"],
    [720, 450, "zoom-equivalent"],
  ]) {
    await viewport(width, height);
    assert.equal(
      await evaluate("document.documentElement.scrollWidth <= innerWidth"),
      true,
      `No overflow at ${width}`,
    );
    await snapshot(name);
  }
  await viewport(390, 844);
  await evaluate(
    "window.detailQA.donor.contact_visible=false; window.detailQA.donor.can_act=false; window.detailQA.donor.contact_via='Jordan Lee'",
  );
  await refresh();
  await until(
    "document.querySelector('.contact-via')?.textContent.trim() === 'Contact via Jordan Lee'",
  );
  assert.equal(
    await evaluate(
      "document.body.innerHTML.includes('alex@example.test') || document.body.innerHTML.includes('+1 602') || document.body.innerHTML.includes('Interested in supporting')",
    ),
    false,
    "Restricted fields absent from DOM",
  );
  assert.equal(
    await evaluate("document.querySelectorAll('a[href^=mailto],a[href^=tel]').length"),
    0,
  );
  assert.equal(
    await evaluate("document.querySelectorAll('.trail-event').length"),
    6,
    "History stays visible",
  );
  await snapshot("mobile-restricted");
  await evaluate("window.detailQA.donor.contact_visible=true; window.detailQA.donor.can_act=false");
  await refresh();
  await until("document.querySelector('.contact-details')");
  assert.equal(
    await evaluate("document.querySelectorAll('a[href^=mailto],a[href^=tel]').length"),
    0,
    "can_act independently gates outreach",
  );
  await evaluate(
    "window.detailQA.donor.contact_visible=true; window.detailQA.donor.can_act=true; window.detailQA.donor.do_not_contact=true",
  );
  await refresh();
  await until("document.querySelector('.contact-via')?.textContent.includes('Do not contact')");
  assert.equal(
    await evaluate("document.querySelectorAll('a[href^=mailto],a[href^=tel]').length"),
    0,
  );
  await evaluate(
    "window.detailQA.events=[]; window.detailQA.donor.recent_gifts=[]; window.detailQA.donor.next_step_title=null; window.detailQA.donor.owner=null; window.detailQA.donor.email=null; window.detailQA.donor.phone=null; window.detailQA.donor.notes=null",
  );
  await refresh();
  await until("document.body.textContent.includes('The story starts here')");
  assert.equal(
    await evaluate(
      "[...document.querySelectorAll('.contact-details dd')].every(el=>el.textContent==='Not provided')",
    ),
    true,
    "Missing contact values are explicit",
  );
  assert.ok(
    await evaluate(
      "document.body.textContent.includes('No linked gifts recorded yet') && document.body.textContent.includes('Not assigned')",
    ),
  );
  for (const status of [401, 403, 500, 501]) {
    await evaluate(`window.detailQA.timelineStatus=${status}`);
    await refresh();
    await until("document.querySelector('#relationship-timeline [role=alert]')");
    assert.ok(await evaluate("Boolean(document.querySelector('.giving-summary'))"));
    await evaluate("window.detailQA.timelineStatus=200");
    if (status === 401) await refresh();
    else await clickText("Try again");
    await until("!document.querySelector('[role=alert]')");
  }
  for (const status of [401, 403, 404, 500, 501]) {
    await evaluate(`window.detailQA.detailStatus=${status}`);
    await refresh();
    await until(
      status === 404
        ? "document.body.textContent.includes('Donor not found')"
        : "document.querySelector('[role=alert]')",
    );
    assert.equal(await evaluate("document.querySelector('.giving-summary')"), null);
    await evaluate("window.detailQA.detailStatus=200");
    if (status === 401 || status === 404) await refresh();
    else await clickText("Try again");
    await until("document.querySelector('.giving-summary')");
  }
  await navigate("/donors");
  await until("document.querySelector('.donor-detail-link')");
  await evaluate("document.querySelector('.donor-detail-link').focus()");
  await key("Enter", "Enter", 13);
  await until("document.querySelector('.relationship-timeline')");
  await evaluate("document.querySelector('.dossier-back').click()");
  await until("location.pathname === '/donors' && document.querySelector('.relationship-row')");
  await evaluate("sessionStorage.setItem('detail-delay','800')");
  await call("Page.navigate", { url: "http://127.0.0.1:5173/donors/1" });
  await until("document.querySelector('[aria-label=\"Loading donor detail\"]')");
  await until("document.querySelector('[aria-label=\"Loading relationship timeline\"]')");
  await until("document.querySelector('.relationship-timeline')");
  await evaluate("sessionStorage.removeItem('detail-delay')");
  await navigate();
  await evaluate("window.detailQA.events=window.detailQA.initialEvents.slice(0,1)");
  await refresh();
  await until("document.querySelectorAll('.trail-event').length===1");
  await evaluate(
    "window.detailQA.events=Array.from({length:20},(_,i)=>({...window.detailQA.initialEvents[i%6],entity_id:i}))",
  );
  await refresh();
  await until("document.querySelectorAll('.trail-event').length===20");
  await evaluate(
    "window.detailQA.donor.display_name='The Synthetic Southwestern Community Foundation for Technology and Creative Learning Partnerships'; window.detailQA.events=Array.from({length:205},(_,i)=>({...window.detailQA.initialEvents[i%6],entity_id:i}))",
  );
  await refresh();
  await until("document.querySelectorAll('.trail-event').length===205");
  assert.equal(await evaluate("document.documentElement.scrollWidth <= innerWidth"), true);
  await snapshot("mobile-dense-long-name");
  await call("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-reduced-motion", value: "reduce" }],
  });
  assert.equal(
    await evaluate("getComputedStyle(document.querySelector('.dossier-back')).transitionDuration"),
    "0s",
  );
  assert.deepEqual(errors, []);
  console.log(
    "PASS: detail, all timeline kinds/order, privacy, DNC, empty/error/recovery, directory navigation, keyboard, responsive/dense layouts, reduced motion.",
  );
} finally {
  socket?.close();
  browser.kill();
}
