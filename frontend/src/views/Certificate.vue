<template>
  <main class="sheet-wrap">
    <div class="no-print toolbar container">
      <button class="btn secondary" @click="$router.back()">返回</button>
      <button class="btn" @click="print">打印 / 另存 PDF</button>
    </div>

    <div v-if="loading" class="empty">正在生成凭证…</div>
    <p v-else-if="error" class="upload-error container">{{ error }}</p>

    <article v-else class="sheet" :class="{ watermark: !cert.official }">
      <header class="sheet-head">
        <div>
          <p class="brand">AI 私教 · 合上资料仍会</p>
          <h1>{{ cert.course_title }}</h1>
          <p class="meta">资料指纹 {{ cert.fingerprint || '未记录' }} · {{ cert.source_file }}</p>
        </div>
        <div class="seal" :class="{ official: cert.official, fail: !cert.passed }">
          {{ cert.passed ? (cert.official ? '正式凭证' : '体验凭证') : '未通过' }}
        </div>
      </header>

      <section class="kpis">
        <div>
          <span>理解</span>
          <strong>{{ cert.understood_lessons }}/{{ cert.total_lessons }}</strong>
        </div>
        <div>
          <span>记忆</span>
          <strong>{{ cert.settled_cards }}/{{ cert.total_cards }}</strong>
        </div>
        <div>
          <span>14 日保持</span>
          <strong>{{ cert.retention_14d == null ? '样本不足' : cert.retention_14d + '%' }}</strong>
        </div>
        <div>
          <span>状态</span>
          <strong>{{ cert.completion_label || '已学过，尚未记住' }}</strong>
        </div>
      </section>

      <p class="note">本页不含原文。讲解与卡片绑定上述指纹；资料被替换则凭证作废。没有「已完成」——听过不等于会。</p>

      <h2>答辩摘要</h2>
      <ol class="items">
        <li v-for="item in cert.items" :key="item.index">
          <p class="q">{{ item.question }}</p>
          <p class="a">作答：{{ item.answer_excerpt || '（空）' }}</p>
          <p class="v" :class="item.verdict">{{ verdictLabel(item.verdict) }} {{ item.feedback }}</p>
        </li>
      </ol>

      <footer class="sheet-foot">
        {{ cert.finished_at ? ('结束于 ' + formatTime(cert.finished_at)) : '' }}
        · 本凭证由学习者本人提取生成，不可转让记忆进度
      </footer>
    </article>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const loading = ref(true)
const error = ref('')
const cert = ref({})

onMounted(async () => {
  try {
    cert.value = await api.getCertificate(route.params.defenseId)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})

function print() { window.print() }
function verdictLabel(v) {
  return { mastered: '已提取', partial: '部分提取', not_mastered: '未提取' }[v] || v
}
function formatTime(iso) {
  try { return new Date(iso).toLocaleString() } catch (e) { return iso }
}
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; padding: 20px 24px; }
.sheet-wrap { padding-bottom: 64px; }
.sheet {
  position: relative;
  width: min(800px, calc(100% - 32px));
  margin: 0 auto;
  background: #fffef9;
  border: 1px solid var(--border);
  padding: 48px 52px 40px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.sheet.watermark::before {
  content: '体验 · 非正式';
  position: absolute;
  inset: 35% 0 auto;
  text-align: center;
  font-size: 48px;
  color: rgba(180, 83, 9, 0.12);
  transform: rotate(-18deg);
  pointer-events: none;
  font-family: var(--font-display);
}
.sheet-head { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--border); padding-bottom: 20px; }
.brand { margin: 0 0 8px; color: var(--brand); font-size: 12px; font-weight: 700; letter-spacing: 0.12em; }
.sheet-head h1 { margin: 0 0 8px; font-family: var(--font-display); font-size: 28px; line-height: 1.3; }
.meta { margin: 0; color: var(--text-secondary); font-size: 13px; }
.seal {
  flex-shrink: 0;
  width: 88px; height: 88px; border-radius: 50%;
  border: 2px solid var(--warning); color: var(--warning);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; text-align: center; padding: 8px;
}
.seal.official { border-color: var(--success); color: var(--success); }
.seal.fail { border-color: var(--danger); color: var(--danger); }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 24px 0; }
.kpis div { background: #f3f0ea; border-radius: 12px; padding: 12px; }
.kpis span { display: block; font-size: 12px; color: var(--text-secondary); }
.kpis strong { font-size: 18px; }
.note { font-size: 13px; color: var(--text-secondary); }
h2 { font-size: 16px; margin: 28px 0 12px; }
.items { padding-left: 18px; }
.items li { margin-bottom: 16px; }
.q { font-weight: 600; margin: 0 0 4px; }
.a, .v { margin: 0; font-size: 13px; color: var(--text-secondary); }
.v.mastered { color: var(--success); }
.v.not_mastered, .v.partial { color: var(--warning); }
.sheet-foot { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-secondary); }
@media (max-width: 700px) {
  .sheet { padding: 28px 20px; }
  .kpis { grid-template-columns: 1fr 1fr; }
  .sheet-head { flex-direction: column; }
}
@media print {
  .sheet { box-shadow: none; width: auto; border: none; }
}
</style>
