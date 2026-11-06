<template>
  <section class="chapter-quiz">
    <div class="q-label">本章收口 · 穿插提取</div>
    <p class="lead">一章结束，混入旧点再考一遍。错了会把该点打回「需补讲」，不会假装学完。</p>

    <div v-if="!quiz && !loading">
      <button class="btn" :disabled="starting" @click="start">{{ starting ? '出题中…' : '开始本章测验' }}</button>
    </div>

    <div v-else-if="quiz && quiz.status === 'passed'" class="feedback mastered">
      本章收口通过。可以继续下一章，或去记忆练习。
    </div>

    <div v-else-if="quiz">
      <p class="meta">{{ currentIndex + 1 }} / {{ questions.length }}</p>
      <p class="q-text">{{ current.question }}</p>
      <textarea v-model="answer" :disabled="busy || doneCurrent" placeholder="用自己的话讲出来"></textarea>
      <div class="q-actions">
        <button class="btn" :disabled="!answer.trim() || busy || doneCurrent" @click="submit">
          {{ busy ? '判断中…' : '提交' }}
        </button>
      </div>
      <div v-if="last" class="feedback" :class="last.verdict">
        <p>{{ last.feedback }}</p>
        <p v-if="last.rollback">该知识点已打回需补讲，请回到目录补上。</p>
      </div>
      <button v-if="doneCurrent && hasNext" class="btn secondary" @click="next">下一题</button>
      <p v-if="quiz.status === 'failed'" class="feedback not_mastered">本章尚未收口，先补讲错过的点。</p>
    </div>
    <p v-if="error" class="upload-error">{{ error }}</p>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({
  chapterId: { type: String, required: true },
})
const emit = defineEmits(['changed'])

const quiz = ref(null)
const loading = ref(false)
const starting = ref(false)
const busy = ref(false)
const answer = ref('')
const currentIndex = ref(0)
const last = ref(null)
const error = ref('')

const questions = computed(() => quiz.value?.questions || [])
const current = computed(() => questions.value[currentIndex.value] || {})
const answered = computed(() => new Set((quiz.value?.results || []).map((r) => r.index)))
const doneCurrent = computed(() => answered.value.has(currentIndex.value))
const hasNext = computed(() => currentIndex.value < questions.value.length - 1)

watch(() => props.chapterId, load, { immediate: true })

async function load() {
  if (!props.chapterId) return
  loading.value = true
  error.value = ''
  try {
    const data = await api.getChapterQuiz(props.chapterId)
    quiz.value = data.quiz
    currentIndex.value = firstUnanswered(data.quiz)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function firstUnanswered(q) {
  if (!q) return 0
  const done = new Set((q.results || []).map((r) => r.index))
  const idx = (q.questions || []).findIndex((_, i) => !done.has(i))
  return idx >= 0 ? idx : 0
}

async function start() {
  starting.value = true
  error.value = ''
  try {
    quiz.value = await api.createChapterQuiz(props.chapterId)
    currentIndex.value = 0
    answer.value = ''
    last.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    starting.value = false
  }
}

async function submit() {
  busy.value = true
  error.value = ''
  try {
    const res = await api.answerChapterQuiz(props.chapterId, currentIndex.value, answer.value)
    last.value = res
    quiz.value = { ...quiz.value, results: res.results, status: res.status }
    if (res.rollback) emit('changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function next() {
  if (!hasNext.value) return
  currentIndex.value += 1
  answer.value = ''
  last.value = null
}
</script>

<style scoped>
.chapter-quiz {
  margin: 24px 0;
  padding: 20px;
  border: 2px solid var(--brand);
  border-radius: var(--radius);
  background: linear-gradient(180deg, #f8f7ff 0%, #fffcf7 100%);
}
.lead, .meta { color: var(--text-secondary); font-size: 14px; }
.q-text { font-size: 16px; font-weight: 600; margin: 8px 0 12px; }
textarea {
  width: 100%; min-height: 80px; border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; font: inherit;
}
.q-actions { margin: 12px 0; }
.upload-error { color: var(--danger); font-size: 14px; }
</style>
