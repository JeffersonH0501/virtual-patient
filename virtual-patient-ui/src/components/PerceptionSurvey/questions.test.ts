import {expect, it} from 'vitest';
import {evaluation, evaluationTitles, experience, sus} from './questions';
it('keeps the ten SUS items in their original order with positive odd and negative even statements', () => {
  expect(sus.map(({id}) => id)).toEqual(Array.from({length: 10}, (_, index) => `SUS-${String(index + 1).padStart(2, '0')}`));
  expect(sus[0].text.en).toBe('I think that I would like to use this system frequently');
  expect(sus[1].text.en).toBe('I found the system unnecessarily complex');
  expect(sus[2].text.en).toBe('I thought the system was easy to use');
  expect(sus[3].text.en).toBe('I think that I would need the support of a technical person to be able to use this system');
  expect(sus[9].text.en).toBe('I needed to learn a lot of things before I could get on with this system');
  expect(sus[1].text.es).toBe('Considero que esta herramienta es innecesariamente compleja');
  // The instrument is not reworded for the virtual patient.
  expect(sus.some(({text}) => /paciente|patient|chatbot/i.test(`${text.es} ${text.en}`))).toBe(false);
});
it('defines the eight own experience items in three dimensions with the agreed Spanish wording', () => {
  expect(experience.map(({id}) => id)).toEqual(['VOZ-01', 'VOZ-02', 'VOZ-03', 'VOZ-04', 'CON-01', 'CON-02', 'CLI-01', 'CLI-02']);
  expect(experience.map(({text}) => text.es)).toEqual([
    'Pude formular mis preguntas oralmente sin dificultades técnicas.',
    'El paciente virtual comprendió adecuadamente mis preguntas habladas.',
    'Las respuestas habladas del paciente virtual fueron fáciles de comprender.',
    'La voz del paciente virtual sonó natural durante la entrevista.',
    'El tiempo de espera para recibir las respuestas del paciente fue adecuado.',
    'El paciente mantuvo la coherencia con la información mencionada anteriormente.',
    'La conversación se asemejó a una entrevista clínica con un paciente real.',
    'La interacción hablada con el paciente virtual me resultó útil para practicar mis habilidades de comunicación durante la anamnesis clínica.',
  ]);
  expect(new Set(experience.map(({group}) => group?.es)).size).toBe(3);
  expect(experience.every(({text}) => text.en.length > 0)).toBe(true);
});
it('keeps the twelve EVA items and their titles independent of the other blocks', () => {
  expect(evaluation.map(({id}) => id)).toEqual(Array.from({length: 12}, (_, index) => `EVA-${String(index + 1).padStart(2, '0')}`));
  expect(evaluationTitles).toHaveLength(evaluation.length);
});
