export const sliceKey = (product, skin, scene) => `${product}|${skin}|${scene}`;

export function getSlice(snapshot, product, skin, scene) {
  return snapshot?.slices?.[sliceKey(product, skin, scene)] ?? null;
}

export function buildEvidenceIndex(records = []) {
  const index = new Map();
  for (const record of records) {
    for (const feature of record.features ?? []) index.set(feature.feature_id, {record, feature});
  }
  return index;
}

export function highlightEvidence(text = '', evidence = '') {
  if (!evidence) return [{text, match: false}];
  const start = text.indexOf(evidence);
  if (start < 0) return [{text, match: false}];
  const parts = [];
  if (start) parts.push({text: text.slice(0, start), match: false});
  parts.push({text: evidence, match: true});
  if (start + evidence.length < text.length) parts.push({text: text.slice(start + evidence.length), match: false});
  return parts;
}

export function metricFor(slice, category, sentiment) {
  return slice?.metrics?.find(metric => metric.category === category && metric.sentiment === sentiment) ?? null;
}

export const percent = value => `${(Number(value || 0) * 100).toFixed(1)}%`;

export function leadingMetrics(slice, sentiment, limit = 6) {
  return [...(slice?.metrics ?? [])]
    .filter(metric => metric.sentiment === sentiment)
    .sort((a, b) => b.mention_count - a.mention_count || a.category.localeCompare(b.category, 'zh-CN'))
    .slice(0, limit);
}
