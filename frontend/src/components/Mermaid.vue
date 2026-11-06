<template>
  <div v-if="code" class="diagram-box">
    <div class="diagram-scroll">
      <div v-html="svg" style="display:inline-block"></div>
    </div>
    <div class="cap">示意图</div>
  </div>
</template>

<style scoped>
.diagram-scroll {
  overflow-x: auto;
  max-width: 100%;
  -webkit-overflow-scrolling: touch;
}
.diagram-box {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
  margin: 20px 0;
}
.cap { font-size: 12px; color: var(--text-secondary); margin-top: 8px; }
</style>

<script setup>
import { ref, watch } from 'vue'
import mermaid from 'mermaid'

const props = defineProps({ code: { type: String, default: '' } })
const svg = ref('')

mermaid.initialize({ startOnLoad: false, theme: 'neutral' })

let seq = 0

async function render(code) {
  if (!code) return
  seq += 1
  const id = 'mermaid-' + seq
  try {
    const { svg: s } = await mermaid.render(id, code)
    svg.value = s
  } catch (e) {
    svg.value = '<p style="color:#ef4444">图渲染失败</p>'
  }
}

watch(() => props.code, render, { immediate: true })
</script>
