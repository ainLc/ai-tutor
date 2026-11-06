<template>
  <div class="question-card" v-if="question">
    <div class="q-label">过关检查 · 请用自己的话回答</div>
    <div class="q-text">{{ question }}</div>

    <textarea
      v-model="answer"
      placeholder="用你自己的话讲出来，检验是否真的理解了…"
      :disabled="submitted && verdict === 'mastered'"
    ></textarea>

    <div class="q-actions">
      <button class="btn" @click="submit" :disabled="!answer.trim() || loading || submitted">
        {{ loading ? 'AI 判断中…' : '提交答案' }}
      </button>
      <button
        v-if="submitted && verdict !== 'mastered' && mode !== 'pretest'"
        class="btn secondary"
        @click="askReteach"
        :disabled="loading"
      >听补讲</button>
      <button
        v-if="submitted && verdict !== 'mastered' && mode !== 'pretest'"
        class="btn secondary"
        @click="$emit('debt')"
      >标记欠账并离开</button>
    </div>

    <div v-if="feedback" class="feedback" :class="verdict">
      <div v-if="verdict === 'mastered'">已理解</div>
      <div v-else-if="verdict === 'partial'">部分掌握 · 需要补讲后再测</div>
      <div v-else>还没掌握 · 需要换个角度再讲</div>
      <p style="margin:6px 0 0">{{ feedback }}</p>
      <p v-if="explanation" style="margin:8px 0 0; opacity:0.9">{{ explanation }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  question: { type: String, default: '' },
  lessonId: { type: String, default: '' },
  mode: { type: String, default: 'gate' },
})
const emit = defineEmits(['mastered', 'reteach', 'debt', 'pretest-fail'])

const answer = ref('')
const loading = ref(false)
const submitted = ref(false)
const verdict = ref('')
const feedback = ref('')
const explanation = ref('')
const gap = ref('')

watch(() => props.question, () => {
  submitted.value = false
  feedback.value = ''
  explanation.value = ''
  verdict.value = ''
  gap.value = ''
  answer.value = ''
})

async function submit() {
  if (!answer.value.trim()) return
  loading.value = true
  try {
    const res = props.mode === 'pretest'
      ? await api.pretestAnswer(props.lessonId, answer.value)
      : await api.answerLesson(props.lessonId, answer.value)
    verdict.value = res.verdict
    feedback.value = res.feedback
    explanation.value = res.explanation
    gap.value = res.gap || ''
    submitted.value = true
    if (res.verdict === 'mastered') {
      emit('mastered', res)
    } else if (props.mode === 'pretest') {
      emit('pretest-fail', res)
    }
  } catch (e) {
    feedback.value = e.message
    verdict.value = 'partial'
    submitted.value = true
    gap.value = e.message
  } finally {
    loading.value = false
  }
}

function askReteach() {
  emit('reteach', { answer: answer.value, gap: gap.value })
}
</script>

<style scoped>
.q-actions { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
