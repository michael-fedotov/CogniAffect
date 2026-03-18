import { ACTION_TYPES } from './annotationActionTypes';
import { initialState } from './annotationInitialState';
import { generateShuffleMaps } from '../utils/annotation/shuffle';

/**
 * @typedef {{
 *   phase: 'welcome' | 'annotating' | 'complete',
 *   annotatorId: string,
 *   scenarios: object[],
 *   shuffleMaps: Record<string, number[]>,
 *   annotations: Record<string, object>,
 *   currentScenarioIndex: number,
 *   lastSavedAt: number | null,
 * }} AnnotationState
 */

/**
 * @param {AnnotationState} state
 * @param {{ type: string, [key: string]: any }} action
 * @returns {AnnotationState}
 */
export function annotationReducer(state, action) {
  switch (action.type) {
    case ACTION_TYPES.START_SESSION: {
      const { annotatorId, scenarios, existingSession } = action;
      if (existingSession) {
        return {
          ...state,
          phase: 'annotating',
          annotatorId,
          scenarios,
          shuffleMaps: existingSession.shuffleMaps || generateShuffleMaps(scenarios),
          annotations: existingSession.annotations || {},
          currentScenarioIndex: existingSession.currentScenarioIndex || 0,
          lastSavedAt: existingSession.savedAt || null,
        };
      }
      return {
        ...state,
        phase: 'annotating',
        annotatorId,
        scenarios,
        shuffleMaps: generateShuffleMaps(scenarios),
        annotations: {},
        currentScenarioIndex: 0,
        lastSavedAt: null,
      };
    }

    case ACTION_TYPES.NAVIGATE: {
      const nextIndex = Math.max(
        0,
        Math.min(state.scenarios.length - 1, action.index),
      );
      const prevScenario = state.scenarios[state.currentScenarioIndex];
      let newAnnotations = { ...state.annotations };

      if (prevScenario) {
        const prev = newAnnotations[prevScenario.scenario_id] || {};
        if (prev.startTime) {
          newAnnotations[prevScenario.scenario_id] = { ...prev, endTime: Date.now() };
        }
      }

      const nextScenario = state.scenarios[nextIndex];
      if (nextScenario) {
        const cur = newAnnotations[nextScenario.scenario_id] || {};
        if (!cur.startTime) {
          newAnnotations[nextScenario.scenario_id] = { ...cur, startTime: Date.now() };
        }
      }

      return { ...state, currentScenarioIndex: nextIndex, annotations: newAnnotations };
    }

    case ACTION_TYPES.UPDATE_ANNOTATION: {
      const { scenarioId, field, value } = action;
      const prev = state.annotations[scenarioId] || {};
      const updated = { ...prev, [field]: value };
      if (!updated.startTime) updated.startTime = Date.now();
      return {
        ...state,
        annotations: { ...state.annotations, [scenarioId]: updated },
      };
    }

    case ACTION_TYPES.MARK_SAVED: {
      return { ...state, lastSavedAt: action.timestamp };
    }

    case ACTION_TYPES.COMPLETE: {
      return { ...state, phase: 'complete' };
    }

    case ACTION_TYPES.RESET: {
      return { ...initialState };
    }

    default:
      return state;
  }
}
