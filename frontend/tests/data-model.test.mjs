import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';

const modulePath = new URL('../src/data-model.js', import.meta.url);
const model = existsSync(modulePath) ? await import(modulePath) : {};

const snapshot = {
  slices: {
    '全部|干皮|早间': {
      summary: {kept_count: 4},
      metrics: [{category: '包装', sentiment: 'negative', mention_count: 2, mention_rate: .5}],
      record_ids: ['R-1'],
      opportunities: []
    },
    '演示产品 A|干皮|早间': {
      summary: {kept_count: 2},
      metrics: [{category: '包装', sentiment: 'negative', mention_count: 1, mention_rate: .5}],
      record_ids: ['R-1'],
      opportunities: []
    }
  },
  records: [{
    record_id: 'R-1',
    product_name: '演示产品 A',
    review_text: '包装好看，但泵头漏液',
    features: [
      {feature_id: 'F-1', category: '包装', sentiment: 'positive', evidence: '包装好看'},
      {feature_id: 'F-2', category: '包装', sentiment: 'negative', evidence: '泵头漏液'}
    ]
  }]
};

test('sliceKey keeps the contract order product|skin|scene', () => {
  assert.equal(typeof model.sliceKey, 'function');
  assert.equal(model.sliceKey('演示产品 A', '干皮', '早间'), '演示产品 A|干皮|早间');
});

test('getSlice only returns a precomputed slice and never aggregates records', () => {
  assert.equal(typeof model.getSlice, 'function');
  assert.equal(model.getSlice(snapshot, '全部', '干皮', '早间').summary.kept_count, 4);
  assert.equal(model.getSlice(snapshot, '演示产品 B', '干皮', '早间'), null);
});

test('buildEvidenceIndex locates a feature and its exact parent record', () => {
  assert.equal(typeof model.buildEvidenceIndex, 'function');
  const index = model.buildEvidenceIndex(snapshot.records);
  assert.equal(index.get('F-2').record.record_id, 'R-1');
  assert.equal(index.get('F-2').feature.evidence, '泵头漏液');
});

test('highlightEvidence escapes unsafe markup and marks only the exact evidence text', () => {
  assert.equal(typeof model.highlightEvidence, 'function');
  const parts = model.highlightEvidence('<img src=x> 泵头漏液', '泵头漏液');
  assert.deepEqual(parts, [
    {text: '<img src=x> ', match: false},
    {text: '泵头漏液', match: true}
  ]);
});

test('metricFor finds an existing precomputed metric without calculating one', () => {
  assert.equal(typeof model.metricFor, 'function');
  const slice = snapshot.slices['演示产品 A|干皮|早间'];
  assert.equal(model.metricFor(slice, '包装', 'negative').mention_count, 1);
  assert.equal(model.metricFor(slice, '价格', 'negative'), null);
});
