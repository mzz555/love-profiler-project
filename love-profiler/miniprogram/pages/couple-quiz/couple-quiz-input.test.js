const assert = require('assert');
const { predictedQuestions, posToValue } = require('./couple-quiz-input.js');

const qs = [
  { question_id: 'A1-1', apply_prediction: true },
  { question_id: 'B1-1', apply_prediction: false },
  { question_id: 'A2-1', apply_prediction: true },
];
assert.deepStrictEqual(predictedQuestions(qs, []).map(q => q.question_id),
  ['A1-1', 'A2-1'], 'predicted 应仅含 apply_prediction');
assert.deepStrictEqual(predictedQuestions(qs, ['A1-1']).map(q => q.question_id),
  ['A2-1'], 'self 跳过的题不进 predicted');

assert.strictEqual(posToValue(50, 0, 300), 50, '无位移=原值');
assert.strictEqual(posToValue(50, 150, 300), 100, '右拖半屏 +50 clamp 100');
assert.strictEqual(posToValue(50, -300, 300), 0, '左拖满屏 clamp 0');
assert.strictEqual(posToValue(0, 0, 0), 0, 'trackWidth 0 安全返回原值');
console.log('couple-quiz-input: 全部通过');
