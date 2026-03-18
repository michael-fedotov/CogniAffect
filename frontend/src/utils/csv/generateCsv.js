function escapeCSV(val) {
  if (val === null || val === undefined) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return '"' + str.replace(/"/g, '""') + '"';
  }
  return str;
}

export function generateCSV(state) {
  const { annotatorId, scenarios, shuffleMaps, annotations } = state;
  const originalIds = ['A', 'B', 'C'];
  const header = [
    'annotation_id',
    'annotator_id',
    'scenario_id',
    'context_snippet',
    'response_a_label',
    'response_b_label',
    'response_c_label',
    'cognitive_most',
    'cognitive_least',
    'cognitive_reasoning',
    'affective_most',
    'affective_least',
    'affective_reasoning',
    'timestamp',
    'session_duration_seconds',
  ].join(',');

  const rows = scenarios
    .map((scenario, idx) => {
      const ann = annotations[scenario.scenario_id];
      if (!ann) return null;

      const map = shuffleMaps[scenario.scenario_id] || [0, 1, 2];
      const scenarioNum = String(idx + 1).padStart(2, '0');
      const annotationId = `${annotatorId}_S${scenarioNum}`;
      const contextSnippet = scenario.context.substring(0, 100).replace(/\n/g, ' ');

      // map[displayIndex] = originalIndex; originalIndex maps to response_id A/B/C
      const aLabel = scenario.ground_truth_labels[originalIds[map[0]]] || '';
      const bLabel = scenario.ground_truth_labels[originalIds[map[1]]] || '';
      const cLabel = scenario.ground_truth_labels[originalIds[map[2]]] || '';

      const duration =
        ann.endTime && ann.startTime
          ? Math.round((ann.endTime - ann.startTime) / 1000)
          : '';
      const timestamp = ann.endTime ? new Date(ann.endTime).toISOString() : '';

      return [
        escapeCSV(annotationId),
        escapeCSV(annotatorId),
        escapeCSV(scenario.scenario_id),
        escapeCSV(contextSnippet),
        escapeCSV(aLabel),
        escapeCSV(bLabel),
        escapeCSV(cLabel),
        escapeCSV(ann.cognitiveMost || ''),
        escapeCSV(ann.cognitiveLeast || ''),
        escapeCSV(ann.cognitiveReasoning || ''),
        escapeCSV(ann.affectiveMost || ''),
        escapeCSV(ann.affectiveLeast || ''),
        escapeCSV(ann.affectiveReasoning || ''),
        escapeCSV(timestamp),
        escapeCSV(duration),
      ].join(',');
    })
    .filter(Boolean);

  return [header, ...rows].join('\n');
}
