<template>
  <section v-if="chapters.length" class="course-map">
    <header class="map-head">
      <div>
        <div class="q-label">课程结构</div>
        <h2 class="map-title">{{ title || '未命名课程' }}</h2>
        <p class="hint">颜色表示理解状态。点知识点即可进去听课，这不是另一套路径。</p>
      </div>
      <div class="map-stats">
        <span><b>{{ understood }}</b> / {{ total }} 已理解</span>
        <span>{{ chapters.length }} 章</span>
      </div>
    </header>

    <ul class="legend">
      <li><i class="dot understood"></i>已理解</li>
      <li><i class="dot learning"></i>学习中</li>
      <li><i class="dot needs_reteach"></i>需补讲</li>
      <li><i class="dot not_started"></i>未开始</li>
    </ul>

    <div class="chapters">
      <article v-for="(ch, i) in chapters" :key="ch.id || i" class="chapter">
        <div class="chapter-bar">
          <h3>{{ i + 1 }}. {{ ch.title }}</h3>
          <span class="chapter-meta">{{ chapterUnderstood(ch) }} / {{ (ch.lessons || []).length }} 已理解</span>
        </div>
        <div class="lessons">
          <button
            v-for="l in ch.lessons"
            :key="l.id"
            type="button"
            class="lesson"
            :class="[statusOf(l), { current: l.id === currentId }]"
            @click="$emit('select', l)"
          >
            <span class="lesson-title">{{ l.title }}</span>
            <span class="lesson-state">{{ labelOf(l) }}</span>
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  title: { type: String, default: '' },
  chapters: { type: Array, default: () => [] },
  currentId: { type: String, default: '' },
})

defineEmits(['select'])

function statusOf(l) {
  const u = l?.understanding || l?.status || 'not_started'
  if (['understood', 'needs_reteach', 'learning', 'not_started'].includes(u)) return u
  if (u === 'completed') return 'understood'
  if (u === 'needs_review') return 'needs_reteach'
  if (u === 'in_progress') return 'learning'
  return 'not_started'
}

function labelOf(l) {
  return {
    understood: '已理解',
    needs_reteach: '需补讲',
    learning: '学习中',
    not_started: '未开始',
  }[statusOf(l)]
}

function chapterUnderstood(ch) {
  return (ch.lessons || []).filter((l) => statusOf(l) === 'understood').length
}

const total = computed(() =>
  (props.chapters || []).reduce((n, ch) => n + (ch.lessons || []).length, 0)
)
const understood = computed(() =>
  (props.chapters || []).reduce((n, ch) => n + chapterUnderstood(ch), 0)
)
</script>

<style scoped>
.course-map {
  margin: 0 0 20px;
  padding: 20px 20px 16px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: var(--shadow);
}
.map-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.map-title {
  margin: 4px 0 6px;
  font-size: 22px;
  font-weight: 650;
  line-height: 1.35;
  font-family: var(--font-display);
}
.hint { font-size: 13px; color: var(--text-secondary); margin: 0; }
.map-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.map-stats b { color: var(--success); font-size: 18px; }
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  list-style: none;
  padding: 12px 0 4px;
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.legend .dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.dot.understood { background: var(--success); }
.dot.learning { background: var(--warning); }
.dot.needs_reteach { background: var(--danger); }
.dot.not_started { background: #94a3b8; }
.chapters { display: flex; flex-direction: column; gap: 14px; }
.chapter {
  padding: 12px 0 0;
  border-top: 1px solid var(--border);
}
.chapter-bar {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}
.chapter-bar h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.4;
}
.chapter-meta { font-size: 12px; color: var(--text-secondary); flex-shrink: 0; }
.lessons { display: flex; flex-wrap: wrap; gap: 8px; }
.lesson {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: min(100%, 200px);
  max-width: 100%;
  flex: 1 1 200px;
  text-align: left;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #f8fafc;
  cursor: pointer;
  font: inherit;
}
.lesson:hover { border-color: #c7d2fe; background: #eef2ff; }
.lesson.current { outline: 2px solid var(--brand); outline-offset: 1px; }
.lesson-title { font-size: 14px; font-weight: 600; line-height: 1.45; color: var(--text); }
.lesson-state { font-size: 12px; }
.lesson.understood { background: #ecfdf5; border-color: #a7f3d0; }
.lesson.understood .lesson-state { color: #047857; }
.lesson.learning { background: #fffbeb; border-color: #fde68a; }
.lesson.learning .lesson-state { color: #b45309; }
.lesson.needs_reteach { background: #fef2f2; border-color: #fecaca; }
.lesson.needs_reteach .lesson-state { color: #b91c1c; }
.lesson.not_started .lesson-state { color: var(--text-secondary); }
@media (max-width: 640px) {
  .lesson { flex: 1 1 100%; }
  .map-stats { align-items: flex-start; }
}
</style>
