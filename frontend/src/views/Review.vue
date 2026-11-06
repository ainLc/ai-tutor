<template>
  <div class="review-page">
    <main class="container review-main" v-if="!loading">
      <div v-if="!cards.length && !finished" class="empty">
        <h3 class="display">今天没有到期的卡片</h3>
        <p v-if="loadError" class="upload-error">{{ loadError }}</p>
        <p v-else>先去学新课，过关后会自动生成要记住的卡片。清完不等于「已完成」。</p>
        <button class="btn" @click="reload">再拉一次今天的队列</button>
        <button class="btn secondary" @click="$router.push('/')">回到今日</button>
      </div>

      <div v-else-if="finished" class="summary card">
        <h2 class="display">本轮练习结束</h2>
        <p class="lead">记住了 {{ remembered }} 张，忘了 {{ forgot }} 张。</p>
        <p v-if="nextPeak" class="muted">下次高峰大约在 {{ nextPeak }}，当天随时可练</p>
        <p v-else class="muted">继续保持，系统会在你快忘的时候再找你。</p>
        <div class="q-actions">
          <button class="btn" @click="$router.push('/')">回到今日</button>
          <button v-if="cards.length" class="btn secondary" @click="reload">再练一轮</button>
        </div>
      </div>

      <div v-else class="session">
        <div class="meta">
          {{ index + 1 }} / {{ cards.length }} · {{ current.course_title }} · {{ current.lesson_title }}
        </div>
        <p v-if="offline" class="offline-banner">正在使用上次缓存的复习队列。评分会在联网后补传。</p>
        <div class="card prompt-card">
          <div class="q-label">先提取，再看答案</div>
          <h2 class="front">{{ current.front }}</h2>
          <div class="voice-row">
            <button class="btn secondary" type="button" @click="speakFront">朗读题面</button>
            <button v-if="phase === 'prompt'" class="btn secondary" type="button" :disabled="listening" @click="dictate">
              {{ listening ? '正在听…' : '口答（说完即停）' }}
            </button>
          </div>
          <textarea
            v-if="phase === 'prompt'"
            v-model="attempt"
            placeholder="可以先写要点、口答，或在心里答完后点显示答案"
          ></textarea>
          <button v-if="phase === 'prompt'" class="btn" @click="phase = 'reveal'">显示答案</button>
        </div>

        <div v-if="phase === 'reveal'" class="card answer-card">
          <div class="q-label">标准提取答案</div>
          <p class="back">{{ current.back }}</p>
          <p v-if="current.source_ref" class="source-ref">原文锚点：{{ current.source_ref }}</p>
          <button class="btn secondary" type="button" @click="speakBack">朗读答案</button>
          <p class="rate-hint">刚才想起来了吗？请诚实自评（这决定下次什么时候再出现）。口答只写入文本，不代替自评。</p>
          <div class="ratings">
            <button class="rate again" :disabled="rating" @click="rate('again')">Again 忘了</button>
            <button class="rate hard" :disabled="rating" @click="rate('hard')">Hard 吃力</button>
            <button class="rate good" :disabled="rating" @click="rate('good')">Good 想起了</button>
            <button class="rate easy" :disabled="rating" @click="rate('easy')">Easy 很轻松</button>
          </div>
          <div v-if="showReteach" class="mini-reteach">
            <button class="btn secondary" @click="doReteach" :disabled="reteaching">
              {{ reteaching ? '补讲中…' : '听 30 秒最小补讲' }}
            </button>
            <div v-if="reteachText" class="reteach-body" v-html="reteachHtml"></div>
            <button v-if="reteachText" class="btn secondary" type="button" @click="speakReteach">朗读补讲</button>
            <button class="btn" style="margin-top:12px" @click="advance">下一张</button>
          </div>
        </div>
      </div>
    </main>
    <div v-else class="empty">加载复习队列…</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import { api } from '../api'
import { listenOnce, speak, stopSpeak } from '../composables/useSpeech'
import { enqueueRating, flushPending, loadReviewQueue, saveReviewQueue } from '../offline/reviewStore'

const loading = ref(true)
const cards = ref([])
const index = ref(0)
const phase = ref('prompt')
const attempt = ref('')
const rating = ref(false)
const finished = ref(false)
const remembered = ref(0)
const forgot = ref(0)
const dues = ref([])
const showReteach = ref(false)
const reteaching = ref(false)
const reteachText = ref('')
const listening = ref(false)
const offline = ref(false)
const loadError = ref('')

const current = computed(() => cards.value[index.value] || {})
const reteachHtml = computed(() => marked(reteachText.value || ''))
const nextPeak = computed(() => {
  if (!dues.value.length) return ''
  const sorted = [...dues.value].filter(Boolean).sort()
  if (!sorted.length) return ''
  try {
    const d = new Date(sorted[Math.floor(sorted.length / 2)])
    return d.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
  } catch (e) {
    return ''
  }
})

async function reload() {
  loading.value = true
  finished.value = false
  index.value = 0
  remembered.value = 0
  forgot.value = 0
  dues.value = []
  loadError.value = ''
  try {
    try {
      await flushPending((id, r) => api.reviewCard(id, r))
    } catch (e) { /* 离线补传失败不挡今天的队列 */ }
    const data = await api.reviewToday()
    const list = Array.isArray(data) ? data : (data?.cards || [])
    cards.value = list
    offline.value = false
    try { await saveReviewQueue(list) } catch (e) { /* 缓存失败仍显示队列 */ }
  } catch (e) {
    loadError.value = e.message || '拉取复习队列失败'
    try {
      const cached = await loadReviewQueue()
      const list = Array.isArray(cached) ? cached : (cached?.cards || [])
      cards.value = list
      offline.value = !!list.length
      if (list.length) loadError.value = ''
    } catch (e2) {
      cards.value = []
    }
  } finally {
    loading.value = false
    resetCard()
  }
}

function resetCard() {
  phase.value = 'prompt'
  attempt.value = ''
  rating.value = false
  showReteach.value = false
  reteachText.value = ''
}

async function rate(r) {
  if (rating.value) return
  rating.value = true
  try {
    let res
    try {
      res = await api.reviewCard(current.value.id, r)
    } catch (e) {
      await enqueueRating(current.value.id, r)
      offline.value = true
      res = {}
    }
    if (res.due_at) dues.value.push(res.due_at)
    if (r === 'again') {
      forgot.value += 1
      showReteach.value = true
      return
    }
    if (r === 'hard' || r === 'good' || r === 'easy') remembered.value += 1
    advance()
  } catch (e) {
    alert(e.message)
    rating.value = false
  }
}

function advance() {
  if (index.value < cards.value.length - 1) {
    index.value += 1
    resetCard()
  } else {
    finished.value = true
  }
}

async function doReteach() {
  reteaching.value = true
  reteachText.value = ''
  try {
    for await (const frame of api.streamReteach(current.value.lesson_id, attempt.value, '复习时提取失败')) {
      if (frame.type === 'text') reteachText.value += frame.content
    }
  } catch (e) {
    reteachText.value = e.message
  } finally {
    reteaching.value = false
  }
}

function speakFront() { speak(current.value.front) }
function speakBack() { speak(current.value.back) }
function speakReteach() { speak(reteachText.value) }

async function dictate() {
  listening.value = true
  try {
    const text = await listenOnce()
    attempt.value = [attempt.value, text].filter(Boolean).join(' ')
  } catch (e) {
    alert(e.message)
  } finally {
    listening.value = false
  }
}

onMounted(() => {
  reload()
  window.addEventListener('online', onOnline)
})
onUnmounted(() => {
  stopSpeak()
  window.removeEventListener('online', onOnline)
})

async function onOnline() {
  try {
    await flushPending((id, r) => api.reviewCard(id, r))
  } catch (e) { /* 保持离线队列 */ }
}
</script>

<style scoped>
.offline-banner { background: #fffbeb; color: #92400e; padding: 10px 12px; border-radius: 8px; font-size: 13px; }
.voice-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; }
.review-main { padding: 32px 0 80px; max-width: 680px; }
.session { display: flex; flex-direction: column; gap: 16px; }
.meta { font-size: 13px; color: var(--text-secondary); }
.prompt-card h2, .front { font-size: 24px; line-height: 1.45; margin: 8px 0 16px; font-family: var(--font-display); }
.empty h3 { font-family: var(--font-display); font-size: 28px; color: var(--text); }
.answer-card .back { font-size: 16px; line-height: 1.7; }
.source-ref { font-size: 13px; color: var(--text-secondary); background: #f1f5f9; padding: 10px 12px; border-radius: 8px; }
.rate-hint { font-size: 13px; color: var(--text-secondary); }
.ratings { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; }
.rate { border: none; border-radius: 10px; padding: 12px 8px; color: #fff; font-weight: 600; cursor: pointer; font-size: 13px; }
.rate:disabled { opacity: 0.55; }
.rate.again { background: var(--danger); }
.rate.hard { background: var(--warning); }
.rate.good { background: var(--success); }
.rate.easy { background: var(--brand); }
.lead { font-size: 18px; }
.muted { color: var(--text-secondary); }
.q-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.mini-reteach { margin-top: 16px; }
.reteach-body { margin-top: 12px; font-size: 15px; }
.review-page textarea { width: 100%; min-height: 80px; border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-family: inherit; margin-bottom: 12px; }
@media (max-width: 640px) {
  .ratings { grid-template-columns: 1fr 1fr; }
}
</style>
