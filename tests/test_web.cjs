const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {ranked, selectRoster, esc} = require('../docs/app.js');
const snapshot = vm.runInNewContext(fs.readFileSync('docs/data.js', 'utf8') + '\n({data:DATA,run:RUN})');
test('browser selection reproduces exported backend roster and terms', () => {
  const selected = selectRoster(ranked(snapshot.data, snapshot.run.weights), snapshot.run.priorities);
  assert.equal(JSON.stringify(selected.map(p => p.c.h)), JSON.stringify(snapshot.run.roster.map(p => p.handle)));
  selected.forEach((p, i) => assert.ok(Math.abs(p.components.total - snapshot.run.roster[i].components.total) < 1e-9));
});
test('saved run and missing-export fallback both render', () => {
  for (const exported of [true, false]) {
    const elements = {};
    const document = {getElementById: id => elements[id] ??= {}, addEventListener: () => {}};
    const source = exported ? fs.readFileSync('docs/data.js', 'utf8') : 'const FALLBACK_DATA = ' + JSON.stringify(snapshot.data);
    vm.runInNewContext(source + '\n' + fs.readFileSync('docs/app.js', 'utf8'), {document});
    assert.ok(elements.roles.innerHTML.includes('Pick 4'));
    assert.ok(elements['run-status'].textContent.includes(exported ? 'SYNTHETIC DEMO' : 'fallback'));
  }
});
test('untrusted metadata is escaped', () => assert.equal(esc('<script>'), '&lt;script&gt;'));
