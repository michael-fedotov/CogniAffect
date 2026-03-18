import { useReducer } from 'react';
import { annotationReducer } from '../state/annotationReducer';
import { initialState } from '../state/annotationInitialState';

/**
 * Owns the top-level session state and provides dispatch.
 * Keep state transitions pure inside the reducer; side-effects
 * (persistence, server sync) live in useAutoSync.
 */
export function useAnnotationSession() {
  const [state, dispatch] = useReducer(annotationReducer, initialState);
  return { state, dispatch };
}
