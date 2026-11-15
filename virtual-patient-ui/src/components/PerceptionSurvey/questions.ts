type Text = {es: string; en: string};
type Question = {id: string; text: Text; caption?: Text; criteria?: Text[]; group?: Text};
const pair = (es: string, en: string): Text => ({es, en});
// System Usability Scale (Brooke, 1996). English wording is the original; the order and the alternation of
// positive (odd) and negative (even) statements must not change because the scoring depends on them. The Spanish
// wording is the version of Sevilla-Gonzalez et al. (2020, JMIR Hum Factors 7(4):e21161) as reproduced by a
// secondary transcription (Universidad de Costa Rica CITIC survey); it has not been compared with the article's
// Multimedia Appendix 2. "herramienta"/"system" are kept: the items are not reworded for the virtual patient.
const susTexts: Text[] = [
  pair('Me gustaría usar esta herramienta frecuentemente', 'I think that I would like to use this system frequently'),
  pair('Considero que esta herramienta es innecesariamente compleja', 'I found the system unnecessarily complex'),
  pair('Considero que la herramienta es fácil de usar', 'I thought the system was easy to use'),
  pair('Considero necesario el apoyo de personal experto para poder utilizar esta herramienta', 'I think that I would need the support of a technical person to be able to use this system'),
  pair('Considero que las funciones de la herramienta están bien integradas', 'I found the various functions in this system were well integrated'),
  pair('Considero que la herramienta presenta muchas contradicciones', 'I thought there was too much inconsistency in this system'),
  pair('Imagino que la mayoría de las personas aprenderían a usar esta herramienta rápidamente', 'I would imagine that most people would learn to use this system very quickly'),
  pair('Considero que el uso de esta herramienta es tedioso', 'I found the system very cumbersome to use'),
  pair('Me sentí muy confiado al usar la herramienta', 'I felt very confident using the system'),
  pair('Necesité saber bastantes cosas antes de poder empezar a usar esta herramienta', 'I needed to learn a lot of things before I could get on with this system'),
];
export const sus: Question[] = susTexts.map((text, index) => ({id: `SUS-${String(index + 1).padStart(2, '0')}`, text}));
// Eight own items on the spoken interaction. They are not a validated scale and have no total score.
const voice = pair('Interacción mediante voz', 'Voice interaction');
const conversation = pair('Calidad conversacional', 'Conversation quality');
const clinical = pair('Simulación clínica', 'Clinical simulation');
export const experience: Question[] = [
  {id: 'VOZ-01', group: voice, text: pair('Pude formular mis preguntas oralmente sin dificultades técnicas.', 'I was able to ask my questions aloud without technical difficulties.')},
  {id: 'VOZ-02', group: voice, text: pair('El paciente virtual comprendió adecuadamente mis preguntas habladas.', 'The virtual patient understood my spoken questions adequately.')},
  {id: 'VOZ-03', group: voice, text: pair('Las respuestas habladas del paciente virtual fueron fáciles de comprender.', 'The virtual patient’s spoken answers were easy to understand.')},
  {id: 'VOZ-04', group: voice, text: pair('La voz del paciente virtual sonó natural durante la entrevista.', 'The virtual patient’s voice sounded natural during the interview.')},
  {id: 'CON-01', group: conversation, text: pair('El tiempo de espera para recibir las respuestas del paciente fue adecuado.', 'The waiting time to receive the patient’s answers was appropriate.')},
  {id: 'CON-02', group: conversation, text: pair('El paciente mantuvo la coherencia con la información mencionada anteriormente.', 'The patient stayed consistent with the information mentioned earlier.')},
  {id: 'CLI-01', group: clinical, text: pair('La conversación se asemejó a una entrevista clínica con un paciente real.', 'The conversation resembled a clinical interview with a real patient.')},
  {id: 'CLI-02', group: clinical, text: pair('La interacción hablada con el paciente virtual me resultó útil para practicar mis habilidades de comunicación durante la anamnesis clínica.', 'The spoken interaction with the virtual patient was useful for practicing my communication skills during clinical anamnesis.')},
];
export const evaluation: Question[] = [
  {id: 'EVA-01', text: pair('El puntaje y la retroalimentación sobre los criterios generales de la entrevista clínica fueron correctos.', 'The score and feedback on the general criteria of the clinical interview were correct.'), criteria: [
    pair('El doctor saludó al paciente de una manera que lo hizo sentir cómodo.', 'The doctor greeted the patient in a way that made them feel comfortable.'),
    pair('El doctor trató al paciente con respeto.', 'The doctor treated the patient with respect.'),
    pair('El doctor escuchó al paciente sin prejuicios, independientemente de la apariencia, modales, género, raza o forma de hablar (sin comentarios racistas o sexistas).', 'The doctor listened without prejudice regardless of appearance, manners, gender, race or manner of speaking (without racist or sexist comments).'),
    pair('El doctor mantuvo profesionalismo y control emocional, incluso cuando el paciente se comportó inapropiadamente o expresó desacuerdo.', 'The doctor remained professional and emotionally controlled, even when the patient behaved inappropriately or disagreed.'),
    pair('El doctor ayudó al paciente a entender qué cambios de salud esperar en las próximas semanas o meses.', 'The doctor helped the patient understand what health changes to expect in the coming weeks or months.'),
    pair('El doctor explicó cómo la enfermedad podría afectar la capacidad del paciente para trabajar o realizar actividades diarias.', 'The doctor explained how the illness could affect the patient’s ability to work or perform daily activities.'),
    pair('El doctor ayudó a aliviar las preocupaciones del paciente sobre estar gravemente enfermo.', 'The doctor helped alleviate the patient’s concerns about being seriously ill.') ]},
  {id: 'EVA-02', text: pair('El puntaje y la retroalimentación sobre la información obtenida y la pertinencia de las hipótesis planteadas fueron correctos.', 'The score and feedback on the information obtained and the relevance of the hypotheses were correct.')},
  {id: 'EVA-03', text: pair('El puntaje y la retroalimentación sobre la claridad en la comunicación fueron correctos.', 'The score and feedback on clarity of communication were correct.'), criteria: [
    pair('El doctor habló en términos que el paciente podía entender, evitando palabras técnicas.', 'The doctor used terms the patient could understand and avoided technical words.'), pair('El doctor se aseguró de que el paciente entendiera todo lo que se explicó.', 'The doctor ensured the patient understood everything explained.'), pair('El doctor expresó sus opiniones y recomendaciones claramente al paciente.', 'The doctor clearly expressed opinions and recommendations.'), pair('El doctor explicó el nombre de la enfermedad usando palabras que el paciente podía entender.', 'The doctor explained the name of the illness in words the patient could understand.')]},
  {id: 'EVA-04', text: pair('El puntaje y la retroalimentación sobre el interés hacia el paciente fueron correctos.', 'The score and feedback on interest in the patient were correct.'), criteria: [
    pair('El doctor mostró interés en las ideas del paciente sobre su salud.', 'The doctor showed interest in the patient’s ideas about their health.'), pair('El doctor mostró interés genuino y preocupación por el paciente.', 'The doctor showed genuine interest and concern for the patient.'), pair('El doctor proporcionó al paciente información sobre sus preocupaciones, siempre que estuvo dentro de su competencia profesional.', 'The doctor provided information about the patient’s concerns within their professional competence.'), pair('El doctor fue considerado con las necesidades del paciente y las priorizó.', 'The doctor considered and prioritized the patient’s needs.')]},
  {id: 'EVA-05', text: pair('El puntaje y la retroalimentación sobre la empatía fueron correctos.', 'The score and feedback on empathy were correct.'), criteria: [
    pair('El doctor entendió las principales preocupaciones del paciente sobre su salud.', 'The doctor understood the patient’s main health concerns.'), pair('El doctor exploró las emociones del paciente durante la conversación.', 'The doctor explored the patient’s emotions during the conversation.'), pair('El doctor fue amigable y amable con el paciente.', 'The doctor was friendly and kind to the patient.'), pair('El doctor respondió apropiadamente a todos los problemas que el paciente mencionó.', 'The doctor responded appropriately to all problems mentioned by the patient.'), pair('El doctor mostró comprensión hacia el paciente.', 'The doctor showed understanding toward the patient.'), pair('El doctor se dedicó a ayudar al paciente.', 'The doctor was dedicated to helping the patient.')]},
  {id: 'EVA-06', text: pair('El puntaje y la retroalimentación sobre el fomento de una comunicación abierta fueron correctos.', 'The score and feedback on encouraging open communication were correct.'), criteria: [
    pair('El doctor le dio al paciente la oportunidad de expresar lo que realmente tenía en mente.', 'The doctor gave the patient an opportunity to express what was really on their mind.'), pair('El doctor respetó el derecho del paciente a hablar libremente.', 'The doctor respected the patient’s right to speak freely.'), pair('El doctor alentó al paciente a hacer preguntas.', 'The doctor encouraged the patient to ask questions.')]},
  {id: 'EVA-07', text: pair('La retroalimentación proporcionada por el sistema ayudó a identificar aspectos concretos del desempeño que podrían mejorarse en futuras entrevistas clínicas.', 'The system’s feedback helped identify specific aspects of performance that could be improved in future clinical interviews.')},
  {id: 'EVA-08', text: pair('La información sobre mi voz (ritmo, pausas y entonación) me permitió identificar aspectos relevantes de mi forma de comunicarme.', 'The information about my voice (pace, pauses and intonation) helped me identify relevant aspects of how I communicate.')},
  {id: 'EVA-09', text: pair('La información sobre mi conducta no verbal (orientación visual, gestos de cabeza y sonrisa) me permitió identificar aspectos relevantes de mi comportamiento comunicativo.', 'The information about my nonverbal behavior (visual orientation, head gestures and smiling) helped me identify relevant aspects of my communicative behavior.')},
  {id: 'EVA-10', text: pair('Ver juntos lo que dije y cómo lo dije me ayudó a comprender mejor mis fortalezas y oportunidades de mejora.', 'Seeing what I said together with how I said it helped me better understand my strengths and opportunities for improvement.')},
  {id: 'EVA-11', text: pair('Pude entender en qué parte de mi entrevista se basaba cada observación de la retroalimentación.', 'I could understand which part of my interview each feedback observation was based on.')},
  {id: 'EVA-12', text: pair('La retroalimentación describió mi comportamiento sin juzgarme como persona.', 'The feedback described my behavior without judging me as a person.')},
];
export const evaluationTitles: Text[] = [
  pair('General', 'General'), pair('Completitud', 'Completeness'), pair('Claridad', 'Clarity'),
  pair('Interés en el paciente', 'Interest in the patient'), pair('Empatía hacia el paciente', 'Empathy toward the patient'),
  pair('Comunicación abierta', 'Open communication'), pair('Utilidad formativa', 'Educational usefulness'),
  pair('Voz y ritmo', 'Voice and pace'), pair('Conducta no verbal', 'Nonverbal behavior'), pair('Integración', 'Integration'),
  pair('Trazabilidad', 'Traceability'), pair('Tono de la retroalimentación', 'Feedback tone'),
];
