<template>
  <div class="dash">
    <main class="container">
      <div class="dash-head">
        <h1 class="display">你还记得多少</h1>
        <p>北星是 14 日保持率。公开排行不是主激励。没有「已完成」。</p>
      </div>

      <div v-if="loading" class="empty">加载中…</div>
      <div v-else class="report">
        <div class="kpi-row">
          <div class="kpi">
            <div class="k">14 日保持率</div>
            <div class="v">{{ stats.retention_14d == null ? '样本不足' : stats.retention_14d + '%' }}</div>
            <p class="muted">近 14 天提取成功比例{{ stats.sample_size ? ' · ' + stats.sample_size + ' 次复习' : '' }}</p>
          </div>
          <div class="kpi">
            <div class="k">今日到期</div>
            <div class="v">{{ stats.due_today || 0 }}</div>
            <p class="muted">不练就会掉的卡片</p>
          </div>
          <div class="kpi">
            <div class="k">本周依从</div>
            <div class="v">{{ stats.week_compliance == null ? '—' : stats.week_compliance + '%' }}</div>
            <p class="muted">近 7 天已复习 {{ stats.week_reviews || 0 }} 次</p>
          </div>
        </div>

        <section>
          <h2>最容易忘的 5 个点</h2>
          <div v-if="!(stats.weakest || []).length" class="muted">还没有足够的复习记录。</div>
          <ul class="weak-list">
            <li v-for="w in stats.weakest" :key="w.lesson_id" @click="$router.push('/learn/' + w.course_id)">
              <strong>{{ w.title }}</strong>
              <span>{{ w.course_title }} · Again {{ w.again_count }} 次</span>
            </li>
          </ul>
        </section>

        <section>
          <h2>各课理解 / 记忆</h2>
          <div class="course-list">
            <div v-for="c in stats.courses || []" :key="c.id" class="course-row" @click="$router.push('/learn/' + c.id)">
              <div>
                <strong>{{ c.title }}</strong>
                <p class="muted">{{ c.completion_label }} · 指纹 {{ c.fingerprint || '—' }}</p>
              </div>
              <div class="row-side">
                <DualProgress
                  :understood="c.understood_lessons || 0"
                  :total="c.total_lessons || 0"
                  :settled="c.settled_cards || 0"
                  :cards="c.total_cards || 0"
                  :label="c.completion_label || ''"
                />
                <button class="btn secondary" @click.stop="$router.push('/defense/' + c.id)">合上书答辩</button>
              </div>
            </div>
          </div>
        </section>

        <section>
          <h2>考前风险</h2>
          <p class="muted">已设考试日的课会列在这里；未设的则看理解未满或记忆未稳住的课。</p>
          <ul class="weak-list">
            <li v-for="c in examList" :key="c.id" @click="$router.push('/learn/' + c.id)">
              <strong>{{ c.title }}</strong>
              <span>{{ c.exam_date ? '考试日 ' + c.exam_date : c.completion_label }} · 理解 {{ c.understood_lessons }}/{{ c.total_lessons }}</span>
            </li>
          </ul>
          <div v-if="!examList.length" class="muted">暂时没有明显风险课。可在听课页「课程设置」里指定考试日。</div>
        </section>

        <details class="public-board">
          <summary>其他人的学习概况（不含课程内容）</summary>
          <div class="board">
            <div class="board-card" v-for="(u, i) in users" :key="u.id">
              <div class="name">{{ u.nickname || u.username }}</div>
              <div class="stat">{{ u.completed_lessons }}/{{ u.total_lessons }} 已理解</div>
            </div>
          </div>
        </details>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import DualProgress from '../components/DualProgress.vue'

const stats = ref({})
const users = ref([])
const loading = ref(true)

const examList = computed(() => {
  const dated = stats.value.exam_risks || []
  if (dated.length) return dated
  const list = stats.value.courses || []
  return list.filter((c) => {
    const total = c.total_lessons || 0
    const understood = c.understood_lessons || 0
    const cards = c.total_cards || 0
    const settled = c.settled_cards || 0
    if (!total) return false
    if (understood < total) return true
    if (cards && settled / cards < 0.5) return true
    return false
  }).slice(0, 8)
})

onMounted(async () => {
  try {
    stats.value = await api.reviewStats()
    users.value = await api.dashboard()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dash-head { padding: 36px 0 28px; }
.dash-head h1 { font-size: 32px; margin: 0 0 6px; }
.dash-head p { color: var(--text-secondary); margin: 0; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }
.kpi { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: var(--shadow); }
.k { font-size: 12px; color: var(--brand); font-weight: 600; letter-spacing: 0.06em; }
.v { font-size: 36px; font-weight: 700; margin: 6px 0; font-family: var(--font-display); }
.muted { color: var(--text-secondary); font-size: 13px; }
section { margin-bottom: 36px; }
h2 { font-size: 18px; margin: 0 0 12px; font-family: var(--font-display); }
.weak-list { list-style: none; padding: 0; margin: 0; }
.weak-list li { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; margin-bottom: 8px; cursor: pointer; box-shadow: var(--shadow); }
.weak-list span { display: block; font-size: 13px; color: var(--text-secondary); }
.course-row { display: grid; grid-template-columns: 1fr 240px; gap: 16px; align-items: center; background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 16px; margin-bottom: 8px; cursor: pointer; box-shadow: var(--shadow); }
.row-side { display: flex; flex-direction: column; gap: 8px; align-items: stretch; }
.public-board { margin: 24px 0 60px; color: var(--text-secondary); }
.board-card { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }
@media (max-width: 640px) {
  .course-row { grid-template-columns: 1fr; }
}
</style>
