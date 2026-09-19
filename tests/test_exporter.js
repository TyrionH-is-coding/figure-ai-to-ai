// Contract tests for the ExtendScript logic; does not launch Illustrator.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const runtime = fs.readFileSync(path.join(__dirname, '../scripts/export_illustrator.jsx'), 'utf8');

function run({ sourceTexts = ['A', 'Ca²⁺'], nativeTexts = sourceTexts, raster = 0, alreadyOpen = false } = {}) {
  let saves = 0, closes = 0;
  const files = new Set(['source.svg']);
  const makeDoc = () => ({
    pathItems: Array(3), compoundPathItems: [], rasterItems: Array(raster), placedItems: [],
    textFrames: nativeTexts.map(contents => ({ contents, characters: [...contents].map(() => ({
      characterAttributes: { textFont: { name: 'Arial' } }
    })) })),
    artboards: [{ artboardRect: [0, 90, 160, 0] }], name: 'result.ai',
    fullName: { fsName: 'source.svg' },
    saveAs(file) { saves++; files.add(file.fsName); this.fullName = file; },
    close: () => closes++, exportFile: () => {}
  });
  const app = {
    version: 'mock', userInteractionLevel: 'original',
    documents: alreadyOpen ? [{ fullName: { fsName: 'source.svg' } }] : [],
    open: makeDoc, redraw: () => {}
  };
  const context = vm.createContext({ app,
    File: function (name) { this.exists = files.has(name); this.fsName = name; },
    IllustratorSaveOptions: function () {}, ExportOptionsPNG24: function () {},
    UserInteractionLevel: { DONTDISPLAYALERTS: 0 },
    SaveOptions: { DONOTSAVECHANGES: 0 }, ExportType: { PNG24: 0 }
  });
  vm.runInContext(runtime, context);
  const config = { svg: 'source.svg', ai: 'result.ai', png: 'result.png', dpi: 300,
    expectedText: sourceTexts.length, sourceTexts };
  let result;
  for (const stage of ['validate', 'save', 'close-created', 'verify-export']) {
    config.stage = stage;
    if (stage === 'save') app.activeDocument = makeDoc();
    if (stage === 'verify-export') {
      app.activeDocument = makeDoc(); app.activeDocument.fullName.fsName = 'result.ai';
    }
    result = vm.runInContext(`exportScientificFigure(${JSON.stringify(config)})`, context);
    if (!result.startsWith('OK|')) break;
    if (stage === 'save') config.imported = JSON.parse(result.slice(3)).imported;
  }
  assert.equal(app.userInteractionLevel, 'original');
  return { result, saves, closes };
}

let out = run();
assert.ok(out.result.startsWith('OK|'));
assert.equal(out.saves, 1); assert.equal(out.closes, 1);
assert.equal(JSON.parse(out.result.slice(3)).reopened.sourceCharactersMatch, true);

out = run({ sourceTexts: ['Ca²⁺'], nativeTexts: ['Ca', '²⁺'] });
assert.ok(out.result.startsWith('OK|'));
assert.equal(JSON.parse(out.result.slice(3)).reopened.splitTextRequiresVisualReview, true);

out = run({ nativeTexts: ['A', 'Ca2+'] });
assert.ok(out.result.startsWith('ERROR|')); assert.equal(out.saves, 0);

out = run({ raster: 1 });
assert.ok(out.result.startsWith('ERROR|')); assert.equal(out.saves, 0);

out = run({ alreadyOpen: true });
assert.ok(out.result.startsWith('ERROR|')); assert.equal(out.saves, 0); assert.equal(out.closes, 0);
console.log('5 exporter contract tests passed (mock, not Illustrator runtime verification).');
