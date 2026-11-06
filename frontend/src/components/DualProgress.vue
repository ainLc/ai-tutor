<template>
  <div class="dual-progress">
    <div class="row">
      <span class="lbl understand">理解</span>
      <div class="track"><div class="fill understand" :style="{ width: understandPct + '%' }"></div></div>
      <span class="num">{{ understood }}/{{ total }}</span>
    </div>
    <div class="row">
      <span class="lbl memory">记忆</span>
      <div class="track"><div class="fill memory" :style="{ width: memoryPct + '%' }"></div></div>
      <span class="num">{{ settled }}/{{ cards }}</span>
    </div>
    <p class="label" :class="{ sting: isUnremembered }">{{ label }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  understood: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
  settled: { type: Number, default: 0 },
  cards: { type: Number, default: 0 },
  label: { type: String, default: '' },
})

const isUnremembered = computed(() => (props.label || '').includes('尚未记住'))
const understandPct = computed(() => {
  if (!props.total) return 0
  return Math.round((props.understood / props.total) * 100)
})
const memoryPct = computed(() => {
  if (!props.cards) return 0
  return Math.round((props.settled / props.cards) * 100)
})
</script>

<style scoped>
.dual-progress { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 8px; }
.lbl { font-size: 11px; width: 32px; flex-shrink: 0; font-weight: 600; }
.lbl.understand { color: var(--success); }
.lbl.memory { color: var(--brand); }
.track { flex: 1; height: 8px; background: var(--paper-deep); border-radius: 999px; overflow: hidden; }
.fill { height: 100%; border-radius: 999px; }
.fill.understand { background: var(--success); }
.fill.memory { background: var(--brand); }
.num { font-size: 11px; color: var(--text-secondary); width: 48px; text-align: right; font-variant-numeric: tabular-nums; }
.label { margin: 2px 0 0; font-size: 12px; color: var(--text-secondary); font-weight: 600; }
.label.sting { color: var(--warning); }
</style>
