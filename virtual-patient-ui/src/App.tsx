import {AppRouter} from './AppRouter';
import {MotionProvider} from './components/common/Motion';
import {useInputViewport} from './hooks/useInputViewport';

function App() {
  useInputViewport();
  return (
    <MotionProvider>
      <div data-ui-motion="app" className="contents">
        <AppRouter />
      </div>
    </MotionProvider>
  );
}

export default App;
