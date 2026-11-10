import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, render, screen} from '@testing-library/react';
import {TurnEvidenceDetails} from './TurnEvidenceDetails';
import {RecapTurn} from '../../types/recording';

vi.mock('react-i18next', () => ({useTranslation: () => ({t: (key: string) => key})}));
afterEach(cleanup);

const turn: RecapTurn = {
  turnId: 'synthetic', speaker: 'student', startMs: 0, endMs: 2000,
  transcript: '', inputSource: 'camera_microphone', timingSource: 'block_speech', timingQuality: 'measured',
};
const explanation = 'clinicalChat.recap.gazeOutsideCalibration';

it('explains unavailable gaze from the explicit reason', () => {
  render(<TurnEvidenceDetails turn={{...turn, nonverbalFeatures: {
    baseLabels: {gazeOrientation: {visualAlignmentRatio: {status: 'unavailable', reason: 'outside_calibrated_geometry'}}},
  }}} />);
  expect(screen.queryByText(explanation)).not.toBeNull();
});

it('explains historical gaze exclusions without rewriting stored results', () => {
  render(<TurnEvidenceDetails turn={{...turn, nonverbalFeatures: {
    raw: {gazeObservations: [{state: 'outside_calibrated_geometry'}, {state: 'outside_calibrated_geometry'}, {state: 'eyes_closed'}]},
  }}} />);
  expect(screen.queryByText(explanation)).not.toBeNull();
});

it('does not describe available gaze or missing observations as an invalid framing', () => {
  const {rerender} = render(<TurnEvidenceDetails turn={{...turn, nonverbalFeatures: {
    processed: {interactionGazeRatio: 0.5, medianInteractionDwellMs: 800},
    raw: {gazeObservations: [{state: 'outside_calibrated_geometry'}]},
  }}} />);
  expect(screen.queryByText(explanation)).toBeNull();
  expect(screen.getByText('0.5')).not.toBeNull();
  expect(screen.getByText('800')).not.toBeNull();
  rerender(<TurnEvidenceDetails turn={{...turn, nonverbalFeatures: {raw: {gazeObservations: [null, {state: 'eyes_closed'}]}}}} />);
  expect(screen.queryByText(explanation)).toBeNull();
});
