<template>
  <main class="container defense-page">
    <header class="page-head">
      <p class="kicker">合上书答辩</p>
      <h1 class="display">{{ courseTitle || '合上资料，用自己的话讲' }}</h1>
      <p class="sub">不给选项，不给原文。通过后出具一页掌握凭证，发给导师或主管。这不是听课当场的过关题。</p>
    </header>

    <div v-if="loading" class="empty">正在准备答辩…</div>
    <p v-else-if="error" class="upload-error">{{ error }}</p>

    <section v-else-if="!session" class="gate card">
      <p v-if="!ready">至少理解过关 3 个知识点后才能开场。当前已理解 {{ understood }} 个。</p>
      <p v-else>已理解 {{ understood }} 个知识点。合上资料，大约 8–12 分钟。</p>
      <div class="actions">
        <button class="btn" :disabled="!ready || starting" @click="start">
          {{ starting ? '出题中…' : '开始合上书答辩' }}
        </button>
        <button class="btn secondary" @click="$router.push('/learn/' + courseId)">返回听课</button>
      </div>
    </section>

    <section v-else-if="session.status === 'passed' || session.status === 'failed'" class="result card">
      <p class="kicker">{{ session.status === 'passed' ? '答辩通过' : '尚未通过' }}</p>
      <h2 class="display">{{ session.status === 'passed' ? '合上资料，你讲得出来' : '还不能叫会了' }}</h2>
      <p class="sub">
        {{ session.status === 'passed' ? '可以出具凭证。体验套餐带水印；Pro 为正式页眉。' : '未达 80% 提取通过。回去补讲后再开一场，不会把进度写成学完。' }}
      </p>
      <div class="actions">
        <button v-if="session.status === 'passed' || session.status === 'failed'" class="btn" @click="$router.push('/certificate/' + session.id)">打开凭证</button>
        <button class="btn secondary" @click="restart">再开一场</button>
        <button class="btn secondary" @click="$router.push('/learn/' + courseId)">返回听课</button>
      </div>
    </section>

    <section v-else class="session">
      <div class="meta">{{ currentIndex + 1 }} / {{ questions.length }} · 闭卷 · 请用自己的话</div>
      <article class="card prompt">
        <div class="q-label">提取题</div>
        <h2>{{ current.question }}</h2>
        <textarea v-model="answer" :disabled="busy || doneCurrent" placeholder="合上资料后，把你记得的关键对比、因果和用法写下来。"></textarea>
        <button class="btn" :disabled="!answer.trim() || busy || doneCurrent" @click="submit">
          {{ busy ? '判断中…' : '提交这题' }}
        </button>
        <div v-if="last" class="feedback" :class="last.verdict">{{ last.feedback }}</div>
        <button v-if="doneCurrent && hasNext" class="btn secondary" style="margin-top:12px" @click="next">下一题</button>
      </article>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const courseId = computed(() => route.params.courseId)
const courseTitle = ref('')
const loading = ref(true)
const starting = ref(false)
const busy = ref(false)
const error = ref('')
const ready = ref(false)
const understood = ref(0)
const session = ref(null)
const currentIndex = ref(0)
const answer = ref('')
const last = ref(null)

const questions = computed(() => session.value?.questions || [])
const current = computed(() => questions.value[currentIndex.value] || {})
const answered = computed(() => new Set((session.value?.answers || []).map((a) => a.index)))
const doneCurrent = computed(() => answered.value.has(currentIndex.value))
const hasNext = computed(() => currentIndex.value < questions.value.length - 1)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const course = await api.getCourse(courseId.value)
    courseTitle.value = course.title || ''
    const data = await api.getDefense(courseId.value)
    ready.value = !!data.ready
    understood.value = data.understood || 0
    session.value = data.defense
    currentIndex.value = firstUnanswered(data.defense)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function firstUnanswered(d) {
  if (!d) return 0
  const done = new Set((d.answers || []).map((a) => a.index))
  const idx = (d.questions || []).findIndex((_, i) => !done.has(i))
  return idx >= 0 ? idx : 0
}

async function start() {
  starting.value = true
  error.value = ''
  try {
    session.value = await api.startDefense(courseId.value)
    currentIndex.value = 0
    answer.value = ''
    last.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    starting.value = false
  }
}

async function restart() {
  session.value = null
  await start()
}

async function submit() {
  if (!session.value || !answer.value.trim()) return
  busy.value = true
  try {
    const res = await api.answerDefense(session.value.id, currentIndex.value, answer.value)
    last.value = { verdict: res.verdict, feedback: res.feedback }
    session.value = res.defense
    if (res.status === 'passed' || res.status === 'failed') {
      router.push(`/certificate/${session.value.id}`)
    }
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
.defense-page { padding: 28px 0 80px; max-width: 720px; }
.kicker { margin: 0 0 8px; font-size: 12px; font-weight: 600; color: var(--brand); letter-spacing: 0.06em; }
.page-head h1 { font-size: 32px; margin: 0 0 10px; line-height: 1.25; }
.sub { color: var(--text-secondary); margin: 0 0 24px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.meta { font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; }
.prompt h2 { font-size: 22px; line-height: 1.45; margin: 8px 0 16px; }
.gate p, .result p { margin: 0; }
.result h2 { margin: 0 0 8px; font-size: 28px; }
</style>
