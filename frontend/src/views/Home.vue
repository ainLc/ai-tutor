<template>
  <main class="container home">
    <section v-if="!loading && !courses.length" class="welcome">
      <p class="kicker">先讲懂 · 再过关 · 再记住</p>
      <h1 class="display">合上你的资料，两周后还要能讲</h1>
      <p class="sub">对着原文讲懂，不懂不能过关，过关后按遗忘曲线把该记的送回来。没有「已完成」，只有已理解、尚未记住、已记住。</p>
      <button class="btn" @click="openUpload()">上传将用于过关的那份资料</button>
      <div class="principles">
        <div><strong>对着原文讲</strong><span>讲解必须能指回资料</span></div>
        <div><strong>不懂不能过</strong><span>补讲后再测，不许跳过</span></div>
        <div><strong>按遗忘找你</strong><span>明天打开先复习</span></div>
      </div>
      <div class="demo-progress card">
        <p class="q-label">演示 · 双进度（这不是皮肤）</p>
        <DualProgress :understood="6" :total="8" :settled="2" :cards="10" label="已学过，尚未记住" />
      </div>
    </section>

    <section v-else class="page-head">
      <div>
        <p class="kicker">今日</p>
        <h1 class="display">先清该记的，再学新的</h1>
      </div>
      <div v-if="billing" class="plan-chip">{{ billing.plan_name }} · {{ billing.used_courses }}/{{ billing.max_courses }} 门课</div>
    </section>

    <section class="today-section" v-if="today">
      <div v-if="today.locked_new || today.overloaded" class="circuit-banner">
        <h3>负荷熔断</h3>
        <p>
          你有 {{ today.due_count }} 张今天不练就会掉（阈值 {{ today.circuit_limit || 40 }}）。
          再学新的等于给自己挖坑。
        </p>
        <template v-if="today.locked_new">
          <label>
            <input v-model="ackCircuit" type="checkbox" />
            我知道这会降低 14 日保持率
          </label>
          <button class="btn secondary" :disabled="!ackCircuit || unlocking" @click="unlock">
            {{ unlocking ? '解锁中…' : '知情后继续学新课（今天内有效）' }}
          </button>
        </template>
        <p v-else class="muted">已知情解锁至今天结束。建议仍先清复习。</p>
      </div>

      <div class="today-grid">
        <div class="today-card due" @click="$router.push('/review')">
          <div class="today-kicker">今日复习</div>
          <div class="today-num">{{ today.due_count || 0 }}</div>
          <p>张今天到期 · 今天随时可练</p>
          <button class="btn">开始今天的记忆练习</button>
        </div>
        <div class="today-card">
          <div class="today-kicker">今日欠账</div>
          <div v-if="!(today.debts || []).length" class="muted">没有未过关的知识点</div>
          <ul v-else class="debt-list">
            <li v-for="d in today.debts.slice(0, 4)" :key="d.lesson_id" @click="goLearn(d)">
              {{ d.title }} <span>{{ d.course_title }}</span>
            </li>
          </ul>
        </div>
        <div class="today-card next" :class="{ locked: today.locked_new }" @click="goNextLesson">
          <div class="today-kicker">下一步新课</div>
          <template v-if="today.next_lesson">
            <h3>{{ today.next_lesson.title }}</h3>
            <p class="muted">{{ today.next_lesson.course_title }}</p>
            <button class="btn secondary" :disabled="today.locked_new">{{ today.locked_new ? '新课已锁定' : '继续学这块' }}</button>
          </template>
          <p v-else class="muted">新课已全部理解过关。去合上书答辩，或去记忆练习。</p>
        </div>
      </div>
      <div v-if="(today.exam_risks || []).length" class="exam-banner">
        <strong>临近考试</strong>
        <span v-for="e in today.exam_risks" :key="e.id">
          {{ e.title }} · {{ e.exam_date }}
        </span>
      </div>
    </section>

    <section class="courses-section">
      <div class="section-head">
        <h2 class="section-title">我的课程</h2>
        <span v-if="courses.length" class="count">{{ courses.length }} 门</span>
      </div>

      <div v-if="loading" class="course-grid">
        <div class="skeleton" v-for="i in 3" :key="i"></div>
      </div>

      <div v-else class="course-grid">
        <div v-for="c in courses" :key="c.id" class="course-card" @click="go(c.id)">
          <div class="course-top">
            <div class="course-icon">{{ initial(c) }}</div>
            <span v-if="c.fingerprint" class="fp">指纹 {{ c.fingerprint }}</span>
          </div>
          <div class="course-body">
            <h3 class="course-title">{{ c.title }}</h3>
            <p class="course-src">{{ c.shared_from ? '分享导入' : c.source_file }}</p>
            <p v-if="c.exam_date" class="exam-date">考试日 {{ c.exam_date }}</p>
          </div>
          <DualProgress
            :understood="c.understood_lessons || 0"
            :total="c.total_lessons || 0"
            :settled="c.settled_cards || 0"
            :cards="c.total_cards || 0"
            :label="c.completion_label || '未开始'"
          />
          <div class="course-actions">
            <button class="course-share" @click.stop="share(c)">分享结构</button>
            <button class="course-share defense" @click.stop="$router.push('/defense/' + c.id)">合上书答辩</button>
            <button class="course-del" @click.stop="remove(c.id)">删除</button>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup>
import { inject, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import DualProgress from '../components/DualProgress.vue'

const router = useRouter()
const openUpload = inject('openUpload', () => {})
const courses = ref([])
const loading = ref(true)
const today = ref(null)
const billing = ref(null)
const ackCircuit = ref(false)
const unlocking = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  try {
    courses.value = await api.listCourses()
    try { today.value = await api.today() } catch (e) { today.value = null }
    try { billing.value = await api.getBilling() } catch (e) { billing.value = null }
  } catch (e) {
    if (e.status === 401) { router.push('/login') }
  } finally {
    loading.value = false
  }
}

function initial(c) { return (c.title || '课').trim().charAt(0) }
function goLearn(item) { if (item?.course_id) router.push(`/learn/${item.course_id}`) }
function go(id) { router.push(`/learn/${id}`) }
function goNextLesson() {
  if (today.value?.locked_new) return
  if (today.value?.next_lesson) goLearn(today.value.next_lesson)
}

async function unlock() {
  unlocking.value = true
  try {
    today.value = await api.circuitOverride()
  } catch (e) {
    alert(e.message)
  } finally {
    unlocking.value = false
  }
}

async function share(c) {
  try {
    const res = await api.shareCourse(c.id)
    try { await navigator.clipboard.writeText(res.token) } catch (e) { /* ignore */ }
    alert(`分享码：${res.token}\n已复制。对方导入后记忆进度从零开始。`)
  } catch (e) { alert('分享失败：' + e.message) }
}

async function remove(id) {
  if (!confirm('确定删除这门课程？')) return
  await api.deleteCourse(id)
  await load()
}
</script>

<style scoped>
.home { padding: 28px 0 48px; }
.kicker { font-size: 12px; font-weight: 600; color: var(--brand); letter-spacing: 0.08em; margin: 0 0 8px; }
.welcome { max-width: 680px; padding: 36px 0 24px; }
.welcome h1, .page-head h1 { font-size: 34px; line-height: 1.22; margin: 0 0 14px; }
.sub { color: var(--text-secondary); margin: 0 0 24px; font-size: 16px; }
.principles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 28px; }
.principles div {
  padding: 16px 16px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  display: flex; flex-direction: column; gap: 4px;
  box-shadow: var(--shadow);
}
.principles span { font-size: 13px; color: var(--text-secondary); }
.demo-progress { margin-top: 24px; max-width: 420px; }
.page-head { padding: 12px 0 20px; display: flex; justify-content: space-between; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.plan-chip { font-size: 12px; background: var(--brand-soft); color: var(--brand); padding: 4px 10px; border-radius: 999px; font-weight: 600; }
.today-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-top: 16px; }
.today-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 22px;
  cursor: pointer;
  box-shadow: var(--shadow);
}
.today-card.due { border-color: #c7d2fe; background: linear-gradient(180deg, #eef2ff, #fffcf7); }
.today-card.locked { opacity: 0.72; cursor: not-allowed; }
.today-kicker { font-size: 12px; color: var(--brand); font-weight: 600; letter-spacing: 0.06em; }
.today-num { font-size: 48px; font-weight: 700; line-height: 1.05; margin: 8px 0; font-family: var(--font-display); }
.today-card h3 { margin: 8px 0 4px; font-size: 16px; }
.debt-list { list-style: none; padding: 0; margin: 8px 0 0; }
.debt-list li { padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
.debt-list span { display: block; font-size: 12px; color: var(--text-secondary); }
.muted { color: var(--text-secondary); font-size: 14px; }
.exam-banner { margin-top: 12px; padding: 12px 16px; background: #fff7ed; color: #9a3412; border-radius: 10px; font-size: 14px; display: flex; gap: 12px; flex-wrap: wrap; }
.courses-section { padding: 32px 0 16px; }
.section-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.section-title { font-size: 20px; margin: 0; font-family: var(--font-display); }
.count { font-size: 13px; color: var(--brand); background: var(--brand-soft); padding: 2px 10px; border-radius: 999px; }
.course-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.course-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  cursor: pointer;
  display: flex; flex-direction: column; gap: 12px;
  box-shadow: var(--shadow);
  transition: transform 0.12s ease, border-color 0.12s ease;
}
.course-card:hover { border-color: #c7d2fe; transform: translateY(-2px); }
.course-top { display: flex; justify-content: space-between; align-items: center; }
.course-icon {
  width: 42px; height: 42px; border-radius: 12px;
  background: linear-gradient(180deg, #6366f1, #4338ca);
  color: #fff; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-display); font-size: 18px;
}
.fp { font-size: 11px; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.course-title { font-size: 16px; font-weight: 600; margin: 0 0 4px; }
.course-src, .exam-date { font-size: 12px; color: var(--text-secondary); margin: 0; }
.course-actions { display: flex; gap: 8px; }
.course-share { flex: 1; background: var(--brand-soft); border: none; color: var(--brand); font-size: 12px; padding: 8px; border-radius: 8px; cursor: pointer; font-weight: 600; }
.course-share.defense { background: #ecfdf5; color: var(--success); }
.course-del { background: none; border: 1px solid var(--border); color: var(--text-secondary); cursor: pointer; padding: 8px 12px; border-radius: 8px; }
.course-del:hover { color: var(--danger); border-color: #fecaca; }
.skeleton { height: 180px; border-radius: 16px; background: var(--paper-deep); }
@media (max-width: 768px) {
  .principles { grid-template-columns: 1fr; }
  .welcome h1, .page-head h1 { font-size: 26px; }
}
</style>
