// couple-quiz-input.js — 双轮作答纯逻辑（不依赖 tt，可 node 单测）

function predictedQuestions(questions, skippedIds) {
  const skipped = new Set(skippedIds || []);
  return (questions || []).filter(q => q.apply_prediction && !skipped.has(q.question_id));
}

function posToValue(startValue, deltaX, trackWidth) {
  if (!trackWidth) return startValue;
  const v = Math.round(startValue + (deltaX / trackWidth) * 100);
  return Math.max(0, Math.min(100, v));
}

module.exports = { predictedQuestions, posToValue };
