// Each chapter begins and ends with the complete source figure.
// Layers identify artwork groups that move together with their original labels.
export const diagramScenes = {
  framework: {
    key: 'framework',
    title: 'Framework',
    asset: 'figures/framework.svg',
    fullViewBox: [0, 0, 2160, 1404],
    scenes: [
      { id: 'framework-overview', title: 'Connected decisions', body: 'The book’s synthesis process and the sport framework address connected decisions. This comparison asks how the framework’s guidance can help make synthetic data fit for an intended use.', anchor: 'purpose', focus: 'whole' },
      { id: 'framework-preparation', title: 'Preparation', body: 'First, the production example connects real data, preparation and synthesis. The book also describes generation informed by a process model or analyst knowledge.', anchor: 'book-approach', layers: ['book-production'] },
      { id: 'framework-assessment', title: 'Assessment', body: 'The wider process then distinguishes utility assessment from privacy assurance. Feedback informs synthesis, while a synthesis report and a separate assurance report make the evidence visible.', anchor: 'book-approach', layers: ['book-assessment'] },
      { id: 'framework-objective', title: 'Objective', body: 'The sport framework begins with the problem and the intended use. The user and operating context establish what the synthetic data need to support.', anchor: 'sport-framework', layers: ['dimension-objective'] },
      { id: 'framework-structure', title: 'Structure', body: 'That purpose determines the information to represent: the records, variables and their organisation. Available sources and preparation decisions establish the structure of the dataset.', anchor: 'comparison', layers: ['dimension-structure'] },
      { id: 'framework-generation', title: 'Generation Strategy', body: 'With the required information defined, select how to generate records from the available evidence. The method and its assumptions must support the intended representation and use.', anchor: 'comparison', layers: ['dimension-generation'] },
      { id: 'framework-constraints', title: 'Constraints', body: 'Next, state which combinations are valid, which variation is acceptable and which controls are needed. These decisions connect preparation and generation to the conditions of use.', anchor: 'comparison', layers: ['dimension-constraints'] },
      { id: 'framework-utility', title: 'Utility and Fidelity', body: 'Assess statistical correspondence alongside usefulness for the intended task. Overall resemblance and performance on a particular analysis answer different questions.', anchor: 'evaluation-basis', layers: ['dimension-utility'] },
      { id: 'framework-risk', title: 'Risk and Deployment', body: 'Bring disclosure concerns, assessment evidence, assumptions and limitations into the conditions for use. This dimension connects evaluation to the conditions for responsible application.', anchor: 'sport-framework', layers: ['dimension-risk'] },
      { id: 'framework-evaluation', title: 'Shared evaluation', body: 'Together, task-relevant outcomes, expert and user assessment, and comparison under equivalent conditions examine the framework’s contribution. Their findings identify where guidance needs refinement.', anchor: 'evaluation-basis', layers: ['evaluation-outcomes', 'evaluation-people', 'evaluation-comparison'] },
      { id: 'framework-connection', title: 'Sporting purpose', body: 'The complete view reconnects these decisions and their evaluation. The next chapter gives the framework a specific user, prediction time and judo question.', anchor: 'research-gap', focus: 'whole' },
    ],
  },
  objective: {
    key: 'objective',
    title: 'Objective',
    asset: 'figures/objective.svg',
    fullViewBox: [0, 0, 2400, 1400],
    scenes: [
      { id: 'objective-overview', title: 'Coach’s question', body: 'After official weigh-in, a coach needs to interpret body mass at a specified check the next morning. The objective connects the evidence, hypothetical competition records and the outputs supporting that interpretation.', anchor: 'purpose', focus: 'whole' },
      { id: 'objective-evidence', title: 'Evidence', body: 'The questionnaire describes reported practices, including following-week regain; it does not supply matched next-day competition measurements. Compatible published measurements and explicit judo knowledge inform the additional quantities and their relationships.', anchor: 'evidence', layers: ['questionnaire', 'measurements', 'knowledge'] },
      { id: 'objective-records', title: 'Competition records', body: 'From that evidence, each synthetic row represents one hypothetical athlete at one competition. Its population and context follow the eligibility and measurement settings supported by the selected studies.', anchor: 'population', layers: ['synthetic-records'] },
      { id: 'objective-measurements', title: 'Measurement timing', body: 'Starting mass and official weigh-in mass are available at prediction. The specified hours to the next-day check define the horizon; check mass is the outcome, and regain is check mass minus official mass.', anchor: 'weight-timing', layers: ['measurement-stages', 'prediction-horizon'] },
      { id: 'objective-output', title: 'Intended output', body: 'The intended output combines a next-day mass distribution, regain and the probability of exceeding the applicable IJF random weigh-in limit. The limit is a regulatory comparison, not a physiological bound or the probability of selection for a check.', anchor: 'regulation', layers: ['coach-output', 'regulatory-comparison'] },
      { id: 'objective-connection', title: 'Defined use', body: 'These connections define the prediction question and its evidence. Synthetic evaluation describes performance under the generating assumptions; predictive validity for athletes requires independent measured competition records.', anchor: 'purpose', focus: 'whole' },
    ],
  },
};

export default diagramScenes;
