import { ContextDisplay } from './ContextDisplay';
import { BWSQuestion } from './BWSQuestion';
import { ResponseCard } from '../../components/common/ResponseCard';
import { FinishButton } from '../../components/common/FinishButton';
import { isAnnotationComplete } from '../../utils/annotation/completion';
import { ACTION_TYPES } from '../../state/annotationActionTypes';

const DISPLAY_LABELS = ['A', 'B', 'C'];

export function ScenarioPanel({ state, dispatch }) {
  const { scenarios, currentScenarioIndex, annotations, shuffleMaps } = state;
  const scenario = scenarios[currentScenarioIndex];
  if (!scenario) return null;

  const ann = annotations[scenario.scenario_id] || {};
  const map = shuffleMaps[scenario.scenario_id] || [0, 1, 2];

  const displayResponses = map.map((originalIdx, displayIdx) => ({
    displayLabel: DISPLAY_LABELS[displayIdx],
    text: scenario.responses[originalIdx].text,
  }));

  const isComplete = isAnnotationComplete(ann);
  const isFirst = currentScenarioIndex === 0;
  const isLast = currentScenarioIndex === scenarios.length - 1;

  function updateField(field) {
    return (val) =>
      dispatch({
        type: ACTION_TYPES.UPDATE_ANNOTATION,
        scenarioId: scenario.scenario_id,
        field,
        value: val,
      });
  }

  function handleNavigate(newIndex) {
    const cur = annotations[scenario.scenario_id] || {};
    if (cur.startTime) {
      dispatch({
        type: ACTION_TYPES.UPDATE_ANNOTATION,
        scenarioId: scenario.scenario_id,
        field: 'endTime',
        value: Date.now(),
      });
    }
    dispatch({ type: ACTION_TYPES.NAVIGATE, index: newIndex });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <div className="space-y-6 min-w-0 w-full">
      {/* Scenario header */}
      <div className="flex items-center justify-between">
        <span className="inline-block bg-indigo-100 text-indigo-700 text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wide">
          {scenario.scenario_id.replace('_', ' ')}
        </span>
        {isComplete && (
          <span className="flex items-center gap-1.5 text-emerald-600 text-sm font-semibold">
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 13l4 4L19 7"
              />
            </svg>
            Annotation complete
          </span>
        )}
      </div>

      {/* Context */}
      <div>
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
          Therapy Context
        </h2>
        <ContextDisplay context={scenario.context} />
      </div>

      {/* Responses */}
      <div>
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">
          Response Options
        </h2>
        <div className="space-y-3">
          {displayResponses.map((r) => (
            <ResponseCard key={r.displayLabel} label={r.displayLabel} text={r.text} />
          ))}
        </div>
      </div>

      {/* BWS Questions */}
      <div className="space-y-4 min-w-0">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-500">
          Annotation Questions
        </h2>
        <BWSQuestion
          dimension="cognitive"
          title="Question 1: Cognitive Empathy"
          subtitle="Understanding the client's perspective and situation"
          mostValue={ann.cognitiveMost || ''}
          leastValue={ann.cognitiveLeast || ''}
          reasoning={ann.cognitiveReasoning || ''}
          onMostChange={updateField('cognitiveMost')}
          onLeastChange={updateField('cognitiveLeast')}
          onReasoningChange={updateField('cognitiveReasoning')}
          displayLabels={DISPLAY_LABELS}
        />
        <BWSQuestion
          dimension="affective"
          title="Question 2: Affective Empathy"
          subtitle="Validating the client's emotional experience"
          mostValue={ann.affectiveMost || ''}
          leastValue={ann.affectiveLeast || ''}
          reasoning={ann.affectiveReasoning || ''}
          onMostChange={updateField('affectiveMost')}
          onLeastChange={updateField('affectiveLeast')}
          onReasoningChange={updateField('affectiveReasoning')}
          displayLabels={DISPLAY_LABELS}
        />
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-200">
        <button
          onClick={() => handleNavigate(currentScenarioIndex - 1)}
          disabled={isFirst}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg border-2 border-slate-200 bg-white text-slate-600 font-medium text-sm hover:border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
          Previous
        </button>

        <span className="text-sm text-slate-500 font-medium">
          Scenario {currentScenarioIndex + 1} of {scenarios.length}
        </span>

        {isLast ? (
          <FinishButton state={state} dispatch={dispatch} />
        ) : (
          <button
            onClick={() => handleNavigate(currentScenarioIndex + 1)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white font-medium text-sm hover:bg-indigo-700 transition-all shadow-sm"
          >
            Next
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
