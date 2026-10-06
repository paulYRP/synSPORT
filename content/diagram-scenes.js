// Camera coordinates use the source SVG viewBox, not the PNG dimensions.
// Overview scenes establish the connections; detail scenes make the labels readable.
// mobileViews are ordered [x, y, width, height] subregions within one narrative step.

export const diagramScenes = {
  framework: {
    key: 'framework',
    title: 'Framework',
    asset: 'figures/framework.svg',
    fullViewBox: [0, 0, 2160, 1404],
    scenes: [
      {
        id: 'framework-overview',
        title: 'Connected decisions',
        body: 'The book’s synthesis process and the sport framework address connected decisions. This comparison asks how the framework’s guidance can help make synthetic data fit for an intended use.',
        anchor: 'purpose',
        viewBox: [0, 0, 2160, 1404],
        focus: 'whole',
      },
      {
        id: 'framework-preparation',
        title: 'Preparation',
        body: 'The production example links real data, preparation and synthesis. This is one route: the book also describes generation informed by a process model or analyst knowledge.',
        anchor: 'book-approach',
        viewBox: [20, 125, 1080, 380],
        focus: 'book-production',
        mobileViews: [
          [35, 165, 650, 290],
          [485, 165, 605, 290],
        ],
      },
      {
        id: 'framework-assessment',
        title: 'Assessment',
        body: 'The wider process treats utility assessment and privacy assurance as different responsibilities, with feedback into synthesis. It produces a synthesis report and a separate assurance report.',
        anchor: 'book-approach',
        viewBox: [20, 535, 1080, 725],
        focus: 'book-assessment',
        mobileViews: [
          [175, 555, 580, 570],
          [650, 555, 430, 275],
          [525, 790, 565, 465],
        ],
      },
      {
        id: 'framework-dimensions',
        title: 'Six dimensions',
        body: 'The dimensions connect intended use to representation, generation, constraints, assessment and deployment. Their order guides decisions while allowing evidence to lead back to an earlier question.',
        anchor: 'sport-framework',
        viewBox: [1185, 15, 545, 1250],
        focus: 'dimensions',
        mobileViews: [
          [1210, 15, 485, 635],
          [1210, 660, 485, 595],
        ],
      },
      {
        id: 'framework-evaluation',
        title: 'Shared evaluation',
        body: 'The shared gap is to evaluate the framework’s contribution as well as the generated data. Task-relevant outcomes, expert and user assessment, and comparison under equivalent conditions together inform refinement.',
        anchor: 'evaluation-basis',
        viewBox: [1720, 15, 425, 1320],
        focus: 'evaluation-gap',
        mobileViews: [
          [1780, 120, 365, 635],
          [1780, 640, 365, 650],
        ],
      },
      {
        id: 'framework-connection',
        title: 'Sporting purpose',
        body: 'These connections make the design decisions and their outcomes open to examination. The next chapter gives the framework a specific user, prediction time and judo question.',
        anchor: 'research-gap',
        viewBox: [0, 0, 2160, 1404],
        focus: 'whole',
      },
    ],
  },
  objective: {
    key: 'objective',
    title: 'Objective',
    asset: 'figures/objective.svg',
    fullViewBox: [0, 0, 2400, 1400],
    scenes: [
      {
        id: 'objective-overview',
        title: 'Coach’s question',
        body: 'After official weigh-in, a coach needs to interpret body mass at a specified check the next morning. The objective connects the evidence, hypothetical competition records and the outputs that would support that interpretation.',
        anchor: 'purpose',
        viewBox: [0, 0, 2400, 1400],
        focus: 'whole',
      },
      {
        id: 'objective-evidence',
        title: 'Evidence',
        body: 'The questionnaire describes reported practices, including following-week regain; it does not supply matched next-day competition measurements. Compatible published measurements and explicit judo knowledge inform the additional quantities and their relationships.',
        anchor: 'evidence',
        viewBox: [35, 45, 745, 1240],
        focus: 'source-evidence',
        mobileViews: [
          [55, 165, 695, 660],
          [45, 565, 710, 650],
        ],
      },
      {
        id: 'objective-records',
        title: 'Competition records',
        body: 'Each synthetic row represents one hypothetical athlete at one competition. Its population and context must follow the eligibility and measurement settings supported by the selected studies.',
        anchor: 'population',
        viewBox: [825, 165, 775, 575],
        focus: 'synthetic-records',
      },
      {
        id: 'objective-measurements',
        title: 'Measurement timing',
        body: 'Starting mass and official weigh-in mass are available at prediction; the specified hours to the next-day check define its horizon. Check mass is the outcome, and regain is check mass minus official mass.',
        anchor: 'weight-timing',
        viewBox: [835, 755, 765, 515],
        focus: 'measurement-stages',
        mobileViews: [
          [845, 775, 745, 300],
          [870, 1065, 700, 220],
        ],
      },
      {
        id: 'objective-output',
        title: 'Intended output',
        body: 'The intended output combines a next-day mass distribution, regain and the probability of exceeding the applicable IJF random weigh-in limit. That limit is a regulatory comparison, not a physiological bound or the probability of selection for a check.',
        anchor: 'regulation',
        viewBox: [1640, 165, 725, 1070],
        focus: 'coach-output',
        mobileViews: [
          [1650, 190, 705, 690],
          [1740, 910, 605, 315],
        ],
      },
      {
        id: 'objective-connection',
        title: 'Defined use',
        body: 'The aim is to develop hypothetical competition records for this defined prediction question. Synthetic evaluation describes performance under the generating assumptions; predictive validity for athletes requires independent measured competition records.',
        anchor: 'purpose',
        viewBox: [0, 0, 2400, 1400],
        focus: 'whole',
      },
    ],
  },
};

export default diagramScenes;
