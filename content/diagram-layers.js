// These groups refer to the published figures. Artwork and labels stay together.
// Source SVGs remain intact; the stage displays references to these exact nodes.
const ids = (...names) => ({ ids: names });
const objectiveNodes = (first, last) => ({ children: Array.from({ length: last - first + 1 }, (_, index) => first + index) });

export const diagramLayers = {
  framework: [
    { key: 'book-production', label: 'Preparation and synthesis', box: [36, 157, 1038, 312], axesChildren: [0] },
    { key: 'book-assessment', label: 'Utility and privacy assessment', box: [36, 549, 1038, 698], axesChildren: [1] },
    ...['objective', 'structure', 'generation', 'constraints', 'utility', 'risk'].map((key, index) => ({
      key: `dimension-${key}`, label: ['Objective', 'Structure', 'Generation Strategy', 'Constraints', 'Utility and Fidelity', 'Risk and Deployment'][index],
      box: [1231.2, 82.8 + index * 201.6, 432, 136.8],
      ...ids(`patch_${index + 2}`, `patch_${index + 23}`, `text_${index * 2 + 7}`, `text_${index * 2 + 8}`),
    })),
    { key: 'evaluation-outcomes', label: 'Quantitative outcomes', box: [1824, 434, 213, 83], ...ids('patch_9', 'patch_10', 'patch_11', 'line2d_11', 'text_20') },
    { key: 'evaluation-people', label: 'Expert and user assessment', box: [1829, 645, 238, 67], ...ids('patch_12', 'patch_13', 'patch_14', 'patch_29', 'patch_30', 'patch_31', 'text_21') },
    { key: 'evaluation-comparison', label: 'Comparison with a reference approach', box: [1819, 846, 253, 101], ...ids('patch_32', 'patch_33', 'line2d_12', 'line2d_13', 'line2d_14', 'line2d_15', 'line2d_16', 'line2d_17', 'line2d_18', 'line2d_19', 'text_22') },
  ],
  objective: [
    { key: 'questionnaire', label: 'Questionnaire evidence', box: [90, 234, 511, 289], ...objectiveNodes(10, 12) },
    { key: 'measurements', label: 'Published competition measurements', box: [71, 594, 564, 285], ...objectiveNodes(13, 15) },
    { key: 'knowledge', label: 'Judo domain knowledge', box: [57, 1011, 608, 160], ...objectiveNodes(16, 17) },
    { key: 'synthetic-records', label: 'One athlete at one competition', box: [847, 180, 683, 530], ...objectiveNodes(21, 27) },
    { key: 'measurement-stages', label: 'Body mass at three defined stages', box: [849, 785, 718, 278], ...objectiveNodes(28, 40) },
    { key: 'prediction-horizon', label: 'Hours to the next-day check', box: [918, 1143, 501, 92], ...objectiveNodes(41, 43) },
    { key: 'coach-output', label: 'Prediction after official weigh-in', box: [1625, 195, 750, 720], ...objectiveNodes(45, 52) },
    { key: 'regulatory-comparison', label: 'Random-check limit', box: [1749, 1020, 465, 193], ...objectiveNodes(53, 55) },
  ],
};
