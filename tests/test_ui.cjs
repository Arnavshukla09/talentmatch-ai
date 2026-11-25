// Run with node --test tests/test_ui.cjs (requires jsdom).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const root = path.resolve(__dirname, '..');
const payload = '<img src=x onerror="window.injected=true">';
const report = {
  overall_score: 75, scores: { semantic: 65 },
  top_positive_factors: [payload], top_negative_factors: [payload],
  matched_skills: [payload], missing_skills: [payload],
  feature_vector: { [payload]: payload },
  match_summary: payload,
  suggestions: [{ issue: payload, suggestion: payload, priority: 'high" onclick="alert(1)' }],
  extracted_resume_text: 'Example extracted resume text',
};

async function setup(folder, stored = {}) {
  const isExtension = folder === 'extension';
  const html = readFileSync(path.join(root, folder, isExtension ? 'popup.html' : 'index.html'), 'utf8');
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'https://talentmatch.example/' });
  const w = dom.window;
  const requests = [];
  w.requestAnimationFrame = () => 0;
  w.setTimeout = () => 0;
  w.setInterval = () => 0;
  w.fetch = async (url, options) => {
    requests.push(options);
    return { ok: true, json: async () => report };
  };
  w.chrome = {
    runtime: {},
    tabs: { query: async () => [], create: () => {} },
    storage: { local: {
      get: (keys, callback) => callback(stored),
      set: (value, callback) => { Object.assign(stored, value); callback?.(); },
      remove: (keys, callback) => { keys.forEach(key => delete stored[key]); callback(); },
    } },
  };
  // Let jsdom finish its natural DOMContentLoaded before installing the popup listener.
  await new Promise(resolve => setImmediate(resolve));
  if (isExtension) w.eval(readFileSync(path.join(root, folder, 'theme.js'), 'utf8'));
  w.eval(readFileSync(path.join(root, folder, isExtension ? 'popup.js' : 'main.js'), 'utf8'));
  if (isExtension) w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
  return { dom, w, requests, stored };
}

async function submit(ui, remember = true) {
  const { w } = ui;
  Object.defineProperty(w.document.getElementById('resumeUpload'), 'files', {
    configurable: true, value: [new w.File(['%PDF-1.7'], 'resume.pdf', { type: 'application/pdf' })],
  });
  w.document.getElementById('jobDescription').value = 'Example job description';
  const checkbox = w.document.getElementById('rememberResume');
  if (checkbox) checkbox.checked = remember;
  w.document.getElementById('scoreForm').dispatchEvent(new w.Event('submit', { cancelable: true }));
  await new Promise(resolve => setImmediate(resolve));
}

for (const folder of ['frontend', 'extension']) {
  test(`${folder} renders untrusted report text without creating HTML`, async () => {
    const ui = await setup(folder);
    try {
      await submit(ui);
      assert.equal(ui.requests.length, 1);
      assert.equal(ui.w.document.querySelectorAll('#resultsSection img, #resultsSection [onerror], #resultsSection [onclick]').length, 0);
      assert.ok(ui.w.document.getElementById('strengthsList').textContent.includes(payload));
      assert.equal(ui.w.document.getElementById('matchSummaryText').textContent, payload);
      if (folder === 'frontend') {
        assert.ok(ui.w.document.getElementById('suggestionsList').textContent.includes(payload));
        assert.ok(ui.w.document.querySelector('.priority-medium'));
      }
    } finally { ui.dom.window.close(); }
  });
}

test('extension saves extracted PDF text and restores it after reopening', async () => {
  const ui = await setup('extension');
  let reopened;
  try {
    await submit(ui);
    assert.equal(ui.requests[0].body.get('return_resume_text'), 'true');
    assert.equal(ui.stored.resumeText, report.extracted_resume_text);
    reopened = await setup('extension', ui.stored);
    assert.equal(reopened.w.document.getElementById('fileUploadGroup').style.display, 'none');
    reopened.w.document.getElementById('clearProfileBtn').click();
    assert.equal(ui.stored.resumeText, undefined);
  } finally { ui.dom.window.close(); reopened?.dom.window.close(); }
});

test('extension does not request or store resume text when remembering is off', async () => {
  const ui = await setup('extension');
  try {
    await submit(ui, false);
    assert.equal(ui.requests[0].body.has('return_resume_text'), false);
    assert.equal(ui.stored.resumeText, undefined);
  } finally { ui.dom.window.close(); }
});

test('extension theme matches the website and persists after reopening', async () => {
  const ui = await setup('extension', { 'talentmatch-theme': 'light' });
  let reopened;
  try {
    const rootElement = ui.w.document.documentElement;
    assert.equal(rootElement.getAttribute('data-theme'), 'light');
    const button = ui.w.document.getElementById('themeToggle');
    assert.equal(button.getAttribute('aria-label'), 'Switch to dark theme');
    button.click();
    assert.equal(rootElement.getAttribute('data-theme'), 'dark');
    assert.equal(ui.stored['talentmatch-theme'], 'dark');
    reopened = await setup('extension', ui.stored);
    assert.equal(reopened.w.document.documentElement.getAttribute('data-theme'), 'dark');
    reopened.w.document.getElementById('themeToggle').click();
    assert.equal(reopened.w.document.documentElement.getAttribute('data-theme'), 'light');
    const webTokens = readFileSync(path.join(root, 'frontend/style.css'), 'utf8').replace(/\r\n/g, '\n').split('\n* {')[0].trim();
    const extensionCSS = readFileSync(path.join(root, 'extension/style.css'), 'utf8').replace(/\r\n/g, '\n');
    assert.ok(extensionCSS.startsWith(webTokens));
    assert.ok(!extensionCSS.includes('#2563eb'));
  } finally { ui.dom.window.close(); reopened?.dom.window.close(); }
});
