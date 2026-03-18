import { useAnnotationSession } from './hooks/useAnnotationSession';
import { WelcomeScreen } from './views/WelcomeScreen';
import { AnnotationView } from './views/AnnotationView';
import { CompletionScreen } from './views/CompletionScreen';

export function App() {
  const { state, dispatch } = useAnnotationSession();

  switch (state.phase) {
    case 'annotating':
      return <AnnotationView state={state} dispatch={dispatch} />;
    case 'complete':
      return <CompletionScreen state={state} dispatch={dispatch} />;
    case 'welcome':
    default:
      return <WelcomeScreen dispatch={dispatch} />;
  }
}
