/** @type {import('./annotationReducer').AnnotationState} */
export const initialState = {
  phase: 'welcome',
  annotatorId: '',
  scenarios: [],
  shuffleMaps: {},
  annotations: {},
  currentScenarioIndex: 0,
  lastSavedAt: null,
};
