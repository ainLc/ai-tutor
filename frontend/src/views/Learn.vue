<template>
  <div class="learn">
    <div class="container course-bar">
      <div>
        <p class="bar-kicker">听课</p>
        <strong>{{ course?.title || '加载中…' }}</strong>
        <span v-if="course?.exam_date" class="exam-chip">考试日 {{ course.exam_date }}</span>
      </div>
      <div class="bar-actions">
        <button v-if="dueCount" class="btn" @click="$router.push('/review')">你有 {{ dueCount }} 张今天该记的</button>
        <button class="btn secondary" @click="$router.push('/defense/' + course.id)">合上书答辩</button>
        <button class="btn secondary" @click="showMap = !showMap">{{ showMap ? '收起结构' : '结构总览' }}</button>
        <button class="btn secondary" @click="showSettings = true">课程设置</button>
        <button class="btn btn-ghost toc-toggle" @click="showToc = true">目录</button>
      </div>
    </div>

    <div v-if="showToc" class="toc-drawer-mask" @click.self="showToc = false">
      <div class="toc-drawer">
        <div class="toc-drawer-head">
          <span>课程目录</span>
          <button class="modal-close" @click="showToc = false">✕</button>
        </div>
        <div v-for="ch in course.chapters" :key="ch.id">
          <div class="toc-chapter">{{ ch.title }}</div>
          <div
            v-for="l in ch.lessons"
            :key="l.id"
            class="toc-item"
            :class="{ active: l.id === currentLesson?.id, done: understandingOf(l) === 'understood' }"
            @click="trySelect(l); showToc = false"
          >
            <span class="status-dot" :class="understandingOf(l)"></span>{{ l.title }}
          </div>
        </div>
      </div>
    </div>

    <div class="container learn-layout" v-if="course">
      <aside class="sidebar desktop-only">
        <div v-for="ch in course.chapters" :key="ch.id">
          <div class="toc-chapter">{{ ch.title }}</div>
          <div
            v-for="l in ch.lessons"
            :key="l.id"
            class="toc-item"
            :class="{ active: l.id === currentLesson?.id, done: understandingOf(l) === 'understood' }"
            @click="trySelect(l)"
          >
            <span class="status-dot" :class="understandingOf(l)"></span>{{ l.title }}
          </div>
        </div>
      </aside>

      <main class="content" ref="contentEl">
        <CourseMap
          v-if="showMap"
          :title="course.title"
          :chapters="course.chapters"
          :current-id="currentLesson?.id"
          @select="trySelect"
        />
        <div v-if="lockedNew" class="circuit-banner" style="margin-bottom:16px">
          <h3>新课已锁定</h3>
          <p>今日到期超过阈值。先去记忆练习；欠账补讲仍可进入。强行学新课请回今日页勾选知情。</p>
          <button class="btn secondary" @click="$router.push('/review')">开始记忆练习</button>
        </div>
        <div v-else-if="overloaded" class="overloaded">
          今日复习负担较重。建议先清复习，再学新课。
          <button class="btn secondary" style="margin-left:8px" @click="$router.push('/review')">开始记忆练习</button>
        </div>

        <div v-if="course?.fingerprint" class="fp-line">资料指纹 {{ course.fingerprint }} · {{ course.completion_label }}</div>

        <div v-if="currentLesson" class="lecture-header">
          <h1 style="margin:0 0 8px">{{ currentLesson.title }}</h1>
          <p v-if="currentLesson.summary" class="summary">{{ currentLesson.summary }}</p>
          <div class="header-actions">
            <span class="u-chip" :class="understandingOf(currentLesson)">{{ understandingLabel(currentLesson) }}</span>
            <button class="btn secondary" @click="showSource = !showSource">对照原文</button>
            <button class="btn secondary" @click="reportHallucination">讲的不在资料里</button>
          </div>
        </div>

        <div v-if="showSource" class="source-drawer">
          <div class="q-label">原文摘录</div>
          <div v-if="excerpts.length">
            <div v-for="(ex, i) in excerpts" :key="i" class="excerpt">
              <div v-if="ex.loc" class="loc">{{ ex.loc }}</div>
              <p>{{ ex.excerpt || ex }}</p>
            </div>
          </div>
          <p v-else class="muted">这个知识点还没有原文锚点（可能是旧课程）。</p>
        </div>

        <div class="lecture-content" v-html="rendered"></div>
        <div v-if="streaming" class="cursor" style="color:var(--brand)"></div>

        <Mermaid :code="diagram" />

        <div v-if="reteachMarkdown" class="reteach-box">
          <div class="q-label">补讲 · 换个角度</div>
          <div class="lecture-content" v-html="reteachRendered"></div>
          <div v-if="reteaching" class="cursor" style="color:var(--warning)"></div>
        </div>

        <QuestionCard
          v-if="question"
          :key="question"
          :question="question"
          :lesson-id="currentLesson?.id"
          :mode="pretestMode ? 'pretest' : 'gate'"
          @mastered="onMastered"
          @reteach="onReteach"
          @debt="markDebt"
          @pretest-fail="onPretestFail"
        />

        <div v-if="cards.length" class="cards-preview">
          <div class="q-label">本课将记住的卡片（差的可以删）</div>
          <div v-for="c in cards" :key="c.id" class="mem-card">
            <div>
              <strong>{{ c.front }}</strong>
              <p>{{ c.back }}</p>
              <small>{{ c.source_ref }}</small>
            </div>
            <button class="btn secondary" @click="removeCard(c.id)">这张没价值</button>
          </div>
        </div>
        <div
          v-else-if="understandingOf(currentLesson) === 'understood' && !streaming"
          class="cards-preview"
        >
          <p class="muted" style="margin:0 0 12px">本课暂未生成卡片，可稍后手动生成</p>
          <button class="btn secondary" :disabled="makingCards" @click="makeCards">
            {{ makingCards ? '生成中…' : '手动生成卡片' }}
          </button>
        </div>

        <div v-if="hasLectureContent" class="next-row">
          <button class="btn" @click="goNext">下一知识点 →</button>
        </div>

        <div v-if="error" class="feedback not_mastered">{{ error }}</div>

        <div v-if="!streaming && !currentLesson?.content && !question && !error" class="start-box">
          <button class="btn" :disabled="lockedNew && understandingOf(currentLesson) === 'not_started'" @click="startLecture">
            {{ lockedNew && understandingOf(currentLesson) === 'not_started' ? '新课已锁定' : '开始学习这个知识点' }}
          </button>
          <button class="btn secondary" :disabled="pretesting" @click="startPretest">
            {{ pretesting ? '出题中…' : '我可能已经会（前测）' }}
          </button>
        </div>

        <ChapterQuiz
          v-if="chapterReady && currentChapter"
          :chapter-id="currentChapter.id"
          @changed="reloadCourse"
        />
      </main>
    </div>

    <div v-else-if="!error" class="empty">加载课程中…</div>
    <div v-else class="empty">{{ error }}</div>

    <div v-if="showSettings" class="modal-mask" @click.self="showSettings = false">
      <div class="modal">
        <h3 style="margin-top:0">课程设置</h3>
        <label class="set-label">希望在哪一天仍记住</label>
        <input v-model="examDate" type="date" class="import-input" />
        <label class="set-label">目标保持率</label>
        <select v-model.number="retention" class="import-input">
          <option :value="0.85">85% · 复习更少</option>
          <option :value="0.9">90% · 推荐</option>
          <option :value="0.95">95% · 复习更勤</option>
        </select>
        <p class="muted">考试日前 14 天，到期晚于考试的卡片会提前进入今日队列，避免前一天爆仓。</p>
        <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:16px">
          <button class="btn secondary" @click="showSettings = false">取消</button>
          <button class="btn" :disabled="savingSettings" @click="saveSettings">保存</button>
        </div>
      </div>
    </div>

    <div v-if="lockNext" class="modal-mask" @click.self="lockNext = false">
      <div class="modal">
        <h3 style="margin-top:0">还没过关</h3>
        <p>先完成检查。不懂可以听补讲；也可以标记欠账离开，但不会算作已理解。</p>
        <div style="display:flex; gap:8px; justify-content:flex-end">
          <button class="btn secondary" @click="lockNext = false">继续检查</button>
          <button class="btn" @click="markDebt">标记欠账并离开</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { api } from '../api'
import Mermaid from '../components/Mermaid.vue'
import QuestionCard from '../components/QuestionCard.vue'
import ChapterQuiz from '../components/ChapterQuiz.vue'
import CourseMap from '../components/CourseMap.vue'

const route = useRoute()
const router = useRouter()
const course = ref(null)
const error = ref('')
const lessons = ref([])
const currentIndex = ref(0)
const showToc = ref(false)
const showSource = ref(false)
const lockNext = ref(false)
const dueCount = ref(0)
const overloaded = ref(false)
const lockedNew = ref(false)

const streaming = ref(false)
const markdown = ref('')
const diagram = ref('')
const question = ref('')
const reteachMarkdown = ref('')
const reteaching = ref(false)
const cards = ref([])
const makingCards = ref(false)
const pretestMode = ref(false)
const pretesting = ref(false)
const showMap = ref(false)
const showSettings = ref(false)
const examDate = ref('')
const retention = ref(0.9)
const savingSettings = ref(false)

const currentLesson = computed(() => lessons.value[currentIndex.value])
const rendered = computed(() => marked(markdown.value || ''))
const reteachRendered = computed(() => marked(reteachMarkdown.value || ''))
const contentEl = ref(null)
const excerpts = computed(() => currentLesson.value?.source_excerpts || [])
const hasLectureContent = computed(() => {
  return !!(markdown.value || currentLesson.value?.content)
})
const currentChapter = computed(() => {
  if (!course.value || !currentLesson.value) return null
  return (course.value.chapters || []).find((ch) =>
    (ch.lessons || []).some((l) => l.id === currentLesson.value.id)
  ) || null
})
const chapterReady = computed(() => {
  const ch = currentChapter.value
  if (!ch || !(ch.lessons || []).length) return false
  return ch.lessons.every((l) => understandingOf(l) === 'understood')
})

function understandingOf(l) {
  return l?.understanding || l?.status || 'not_started'
}
function understandingLabel(l) {
  const u = understandingOf(l)
  return { understood: '已理解', needs_reteach: '需补讲', learning: '学习中', not_started: '未开始' }[u] || u
}

onMounted(async () => {
  try {
    const today = await api.today()
    dueCount.value = today.due_count || 0
    overloaded.value = !!today.overloaded
    lockedNew.value = !!today.locked_new
  } catch (e) { /* ignore */ }
  try {
    course.value = await api.getCourse(route.params.courseId)
    examDate.value = course.value.exam_date || ''
    retention.value = course.value.desired_retention || 0.9
    lessons.value = course.value.chapters.flatMap((ch) => ch.lessons)
    const first = lessons.value.findIndex((l) => understandingOf(l) !== 'understood')
    currentIndex.value = first >= 0 ? first : 0
    loadCurrentIntoView()
  } catch (e) {
    error.value = e.message
  }
})

function loadCurrentIntoView() {
  const lesson = lessons.value[currentIndex.value]
  if (!lesson) return
  markdown.value = lesson.content || ''
  diagram.value = lesson.diagram || ''
  question.value = lesson.question || ''
  reteachMarkdown.value = lesson.reteach_content || ''
  cards.value = []
  if (understandingOf(lesson) === 'understood') {
    api.listCards(lesson.id).then((rows) => { cards.value = rows || [] }).catch(() => {})
  }
}

async function startLecture() {
  if (lockedNew.value && understandingOf(currentLesson.value) === 'not_started') {
    error.value = '新课已锁定。请先完成今日记忆练习，或回今日页勾选知情。'
    return
  }
  markdown.value = ''
  diagram.value = ''
  question.value = ''
  error.value = ''
  cards.value = []
  pretestMode.value = false
  streaming.value = true
  try {
    for await (const frame of api.streamLesson(currentLesson.value.id)) {
      if (frame.type === 'text') markdown.value += frame.content
      else if (frame.type === 'diagram') diagram.value = frame.content
      else if (frame.type === 'question') question.value = frame.content
      else if (frame.type === 'error') error.value = frame.content
    }
    if (currentLesson.value) currentLesson.value.understanding = 'learning'
  } catch (e) {
    error.value = e.message
  } finally {
    streaming.value = false
  }
}

function trySelect(l) {
  const idx = lessons.value.findIndex((x) => x.id === l.id)
  if (idx < 0) return
  currentIndex.value = idx
  const lesson = lessons.value[idx]
  if (lesson.content) loadCurrentIntoView()
  else if (lockedNew.value && understandingOf(lesson) === 'not_started') {
    markdown.value = ''
    diagram.value = ''
    question.value = ''
    error.value = '新课已锁定。请先完成今日记忆练习，或回今日页勾选知情。'
  } else startLecture()
}

function goNext() {
  if (understandingOf(currentLesson.value) !== 'understood') {
    lockNext.value = true
    return
  }
  if (currentIndex.value < lessons.value.length - 1) {
    currentIndex.value++
    const lesson = lessons.value[currentIndex.value]
    if (lesson.content) loadCurrentIntoView()
    else startLecture()
  }
}

function onMastered(res) {
  if (currentLesson.value) currentLesson.value.understanding = 'understood'
  cards.value = res.cards || []
  pretestMode.value = false
}

async function startPretest() {
  if (!currentLesson.value) return
  pretesting.value = true
  error.value = ''
  try {
    const res = await api.pretestLesson(currentLesson.value.id)
    pretestMode.value = true
    question.value = res.question
  } catch (e) {
    error.value = e.message
  } finally {
    pretesting.value = false
  }
}

function onPretestFail() {
  pretestMode.value = false
  question.value = ''
  if (currentLesson.value) currentLesson.value.understanding = 'not_started'
}

async function reportHallucination() {
  if (!currentLesson.value) return
  const note = prompt('哪里讲的不在资料里？（可选）') 
  if (note === null) return
  try {
    const res = await api.reportLesson(currentLesson.value.id, note)
    alert(res.message || '已记录')
  } catch (e) {
    alert(e.message)
  }
}

async function saveSettings() {
  savingSettings.value = true
  try {
    course.value = await api.updateCourseSettings(route.params.courseId, {
      exam_date: examDate.value,
      desired_retention: retention.value,
    })
    showSettings.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    savingSettings.value = false
  }
}

async function reloadCourse() {
  try {
    course.value = await api.getCourse(route.params.courseId)
    lessons.value = course.value.chapters.flatMap((ch) => ch.lessons)
    const id = currentLesson.value?.id
    if (id) {
      const idx = lessons.value.findIndex((l) => l.id === id)
      if (idx >= 0) currentIndex.value = idx
    }
  } catch (e) { /* ignore */ }
}

async function makeCards() {
  if (!currentLesson.value) return
  makingCards.value = true
  try {
    cards.value = (await api.createCards(currentLesson.value.id)) || []
  } catch (e) {
    error.value = e.message
  } finally {
    makingCards.value = false
  }
}

async function onReteach({ answer, gap }) {
  reteachMarkdown.value = ''
  reteaching.value = true
  try {
    for await (const frame of api.streamReteach(currentLesson.value.id, answer, gap)) {
      if (frame.type === 'text') reteachMarkdown.value += frame.content
      else if (frame.type === 'error') error.value = frame.content
    }
    const next = await api.retestLesson(currentLesson.value.id)
    question.value = next.question
    if (currentLesson.value) currentLesson.value.understanding = 'needs_reteach'
  } catch (e) {
    error.value = e.message
  } finally {
    reteaching.value = false
  }
}

function markDebt() {
  if (currentLesson.value) currentLesson.value.understanding = 'needs_reteach'
  router.push('/')
}

async function removeCard(id) {
  await api.deleteCard(id)
  cards.value = cards.value.filter((c) => c.id !== id)
}

watch(markdown, async () => {
  await nextTick()
  if (contentEl.value) contentEl.value.scrollTop = contentEl.value.scrollHeight
})
</script>

<style scoped>
.learn-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 32px;
  padding-top: 32px;
  align-items: start;
}
.sidebar {
  position: sticky;
  top: 76px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  padding-right: 8px;
}
.content {
  min-width: 0;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  padding-right: 16px;
  padding-bottom: 80px;
}
.course-bar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 12px; flex-wrap: wrap; padding: 20px 0 0;
}
.bar-kicker { margin: 0; font-size: 12px; color: var(--brand); font-weight: 600; }
.bar-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.exam-chip { margin-left: 8px; font-size: 12px; color: #92400e; background: #fffbeb; padding: 2px 8px; border-radius: 999px; }
.start-box { text-align: center; padding: 48px 0; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.set-label { display: block; margin: 12px 0 6px; font-size: 13px; color: var(--text-secondary); }
.fp-line { font-size: 12px; color: var(--text-secondary); margin-bottom: 12px; }
.lecture-header h1 { font-size: 26px; font-family: var(--font-display); }
.summary { color: var(--text-secondary); background: #f1f5f9; padding: 12px 16px; border-radius: var(--radius-sm); margin: 0 0 16px; }
.header-actions { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.u-chip { font-size: 12px; padding: 4px 10px; border-radius: 999px; background: #f1f5f9; }
.u-chip.understood { background: #ecfdf5; color: #065f46; }
.u-chip.needs_reteach { background: #fef2f2; color: #991b1b; }
.u-chip.learning { background: #fffbeb; color: #92400e; }
.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  margin-right: 8px; background: var(--border); vertical-align: middle;
}
.status-dot.understood { background: var(--success); }
.status-dot.learning { background: var(--warning); }
.status-dot.needs_reteach { background: var(--danger); }
.toc-item.done { color: var(--success); }
.source-drawer, .reteach-box, .cards-preview {
  margin: 16px 0;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #fff;
}
.reteach-box { border-color: var(--warning); background: #fffbeb; }
.excerpt { margin-bottom: 12px; }
.loc { font-size: 12px; color: var(--text-secondary); }
.mem-card { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.mem-card p { margin: 6px 0; font-size: 14px; }
.mem-card small { color: var(--text-secondary); }
.muted { color: var(--text-secondary); }
.overloaded { background: #eef2ff; color: var(--brand); padding: 12px 16px; border-radius: 10px; margin-bottom: 16px; font-size: 14px; }
.next-row { margin: 20px 0 8px; }
.toc-toggle { display: none; }
.toc-drawer-mask {
  position: fixed; inset: 0; background: rgba(15,23,42,0.4); z-index: 50;
  display: flex; justify-content: flex-start;
}
.toc-drawer {
  width: 80%; max-width: 300px; height: 100%; background: #fff;
  overflow-y: auto; padding: 20px 16px; animation: slideIn 0.25s ease;
}
@keyframes slideIn { from { transform: translateX(-100%); } to { transform: translateX(0); } }
.toc-drawer-head { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: 16px; margin-bottom: 12px; }
.modal-close { background: none; border: none; font-size: 18px; color: var(--text-secondary); cursor: pointer; padding: 4px 8px; border-radius: 8px; }
.modal-mask { position: fixed; inset: 0; background: rgba(15,23,42,0.45); display: flex; align-items: center; justify-content: center; z-index: 80; }
.modal { width: 420px; max-width: 92vw; background: #fff; border-radius: 16px; padding: 20px; }

@media (max-width: 768px) {
  .learn { padding-bottom: 40px; }
  .learn-layout { display: block; padding-top: 20px; }
  .sidebar.desktop-only { display: none; }
  .toc-toggle { display: inline-flex; }
  .content {
    max-height: none;
    overflow-y: visible;
    padding-right: 0;
    padding-bottom: 40px;
  }
  .lecture-header h1 { font-size: 20px; }
}
</style>
