<template>
  <main class="container settings">
    <header class="page-head">
      <p class="kicker">设置</p>
      <h1 class="display">套餐、模型与账号</h1>
      <p class="sub">收费卖的是掌握操作系统，不是 Token。点下方卡片可切换预览各档权益。ain 实验室账号不限门课。</p>
    </header>

    <section class="card-block">
      <h2>当前套餐</h2>
      <p v-if="billing" class="status ok">{{ billing.plan_name }} · 已用 {{ billing.used_courses }}/{{ billing.max_courses }} 门课</p>
      <div class="plan-grid">
        <button
          v-for="p in (billing?.plans || [])"
          :key="p.id"
          type="button"
          class="plan"
          :class="{ active: billing?.plan === p.id }"
          @click="switchPlan(p.id)"
        >
          <strong>{{ p.name }}</strong>
          <em>{{ p.price }}</em>
          <span>{{ p.blurb }}</span>
        </button>
      </div>
      <p v-if="planMsg" class="msg" :class="{ err: planErr }">{{ planMsg }}</p>
    </section>

    <header class="page-head nested">
      <h2>模型与接口</h2>
      <p class="sub">选厂商会自动填好地址和常用模型。保存后立刻对拆课、讲课、判题生效。</p>
    </header>

    <p v-if="loaded" class="status" :class="{ ok: form.configured }">
      当前生效：{{ form.model || '未设置' }}
      <span v-if="form.source === 'user'"> · 来自本页</span>
      <span v-else-if="form.source === 'env'"> · 来自服务器 .env</span>
      <span v-else> · 尚未配置 Key</span>
    </p>

    <section class="card-block">
      <h2>厂商</h2>
      <div class="presets">
        <button
          v-for="p in presets"
          :key="p.id"
          type="button"
          class="preset"
          :class="{ active: form.provider === p.id }"
          @click="pickProvider(p)"
        >
          <strong>{{ p.name }}</strong>
          <span>{{ p.hint }}</span>
        </button>
      </div>
    </section>

    <section class="card-block">
      <h2>连接</h2>
      <label class="field">
        <span>接口地址</span>
        <input v-model="form.base_url" placeholder="https://api.example.com/v1" />
      </label>
      <label class="field">
        <span>模型</span>
        <select v-if="currentPreset?.models?.length" v-model="form.model">
          <option v-for="m in currentPreset.models" :key="m" :value="m">{{ m }}</option>
          <option value="__custom">其他（手写）</option>
        </select>
        <input
          v-if="!currentPreset?.models?.length || form.model === '__custom' || customModel"
          v-model="customModel"
          placeholder="模型名，如 deepseek-chat"
          @input="form.model = customModel"
        />
      </label>
      <label class="field">
        <span>API Key</span>
        <input
          v-model="apiKey"
          type="password"
          autocomplete="off"
          :placeholder="form.api_key_masked || '粘贴密钥，保存后不会再明文返回'"
        />
        <small v-if="form.api_key_masked">已保存 {{ form.api_key_masked }}。留空再保存则保持原密钥。</small>
      </label>
      <label class="field">
        <span>温度 {{ form.temperature }}</span>
        <input v-model.number="form.temperature" type="range" min="0" max="1.5" step="0.1" />
      </label>
    </section>

    <p v-if="message" class="msg" :class="{ err: isError }">{{ message }}</p>
    <div class="actions">
      <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存并立即生效' }}</button>
      <button class="btn secondary" :disabled="testing" @click="test">{{ testing ? '测试中…' : '测一次连通' }}</button>
      <button class="btn secondary" :disabled="saving" @click="resetEnv">改回 .env</button>
    </div>

    <section class="card-block danger-zone">
      <h2>删除账号</h2>
      <p class="sub">会删除全部课程、卡片、复习记录、答辩与模型密钥，不可恢复。</p>
      <input v-model="deleteConfirm" class="import-input" placeholder="输入「删除我的账号」以确认" />
      <p v-if="deleteMsg" class="msg err">{{ deleteMsg }}</p>
      <button class="btn danger" style="margin-top:12px" :disabled="deleting" @click="doDelete">
        {{ deleting ? '删除中…' : '永久删除账号' }}
      </button>
      <p class="legal-links">
        <router-link to="/legal/privacy">隐私政策</router-link>
        ·
        <router-link to="/legal/terms">使用条款</router-link>
      </p>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, clearToken } from '../api'

const router = useRouter()

const loaded = ref(false)
const saving = ref(false)
const testing = ref(false)
const message = ref('')
const isError = ref(false)
const apiKey = ref('')
const customModel = ref('')
const presets = ref([])
const form = ref({
  configured: false,
  source: 'none',
  provider: 'deepseek',
  base_url: '',
  model: '',
  temperature: 0.7,
  api_key_masked: '',
})
const billing = ref(null)
const planMsg = ref('')
const planErr = ref(false)
const deleteConfirm = ref('')
const deleteMsg = ref('')
const deleting = ref(false)

const currentPreset = computed(() => presets.value.find((p) => p.id === form.value.provider))

onMounted(load)

async function load() {
  try {
    const data = await api.getLlmSettings()
    apply(data)
    try { billing.value = await api.getBilling() } catch (e) { /* ignore */ }
  } catch (e) {
    fail(e.message)
  } finally {
    loaded.value = true
  }
}

function apply(data) {
  presets.value = data.presets || []
  form.value = {
    configured: data.configured,
    source: data.source,
    provider: data.provider || 'custom',
    base_url: data.base_url || '',
    model: data.model || '',
    temperature: data.temperature ?? 0.7,
    api_key_masked: data.api_key_masked || '',
  }
  const list = currentPreset.value?.models || []
  if (form.value.model && list.length && !list.includes(form.value.model)) {
    customModel.value = form.value.model
    form.value.model = '__custom'
  } else {
    customModel.value = list.includes(form.value.model) ? '' : (form.value.model || '')
  }
  apiKey.value = ''
}

function pickProvider(p) {
  form.value.provider = p.id
  if (p.base_url) form.value.base_url = p.base_url
  if (p.models?.length) {
    form.value.model = p.models[0]
    customModel.value = ''
  } else {
    form.value.model = '__custom'
  }
}

function modelToSave() {
  if (form.value.model === '__custom' || customModel.value) {
    return (customModel.value || form.value.model || '').replace('__custom', '').trim()
  }
  return form.value.model
}

function ok(text) { message.value = text; isError.value = false }
function fail(text) { message.value = text; isError.value = true }

async function save() {
  saving.value = true
  message.value = ''
  try {
    const data = await api.saveLlmSettings({
      provider: form.value.provider,
      base_url: form.value.base_url,
      model: modelToSave(),
      temperature: form.value.temperature,
      api_key: apiKey.value,
    })
    apply(data)
    ok('已保存，当前账号的拆课和讲课会马上用这套配置。')
  } catch (e) {
    fail(e.message)
  } finally {
    saving.value = false
  }
}

async function test() {
  testing.value = true
  message.value = ''
  try {
    const res = await api.testLlmSettings()
    ok(`连通正常 · ${res.model} · 回复：${res.reply || 'ok'}`)
  } catch (e) {
    fail(e.message)
  } finally {
    testing.value = false
  }
}

async function resetEnv() {
  if (!confirm('清除本页配置，改回服务器 .env 里的模型？')) return
  saving.value = true
  try {
    const data = await api.resetLlmSettings()
    apply(data)
    ok('已改回 .env。')
  } catch (e) {
    fail(e.message)
  } finally {
    saving.value = false
  }
}

async function switchPlan(plan) {
  planMsg.value = ''
  planErr.value = false
  try {
    billing.value = await api.switchPlan(plan)
    planMsg.value = `已切换到「${billing.value.plan_name}」（演示，支付未接入）。`
  } catch (e) {
    planErr.value = true
    planMsg.value = e.message
  }
}

async function doDelete() {
  deleteMsg.value = ''
  if (deleteConfirm.value.trim() !== '删除我的账号') {
    deleteMsg.value = '请完整输入「删除我的账号」。'
    return
  }
  if (!confirm('此操作不可恢复。确定删除？')) return
  deleting.value = true
  try {
    await api.deleteAccount('删除我的账号')
    clearToken()
    localStorage.removeItem('ai-tutor-user')
    router.push('/login')
  } catch (e) {
    deleteMsg.value = e.message
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.settings { padding: 28px 0 64px; max-width: 800px; }
.kicker { font-size: 12px; font-weight: 600; color: var(--brand); margin: 0 0 8px; }
.page-head h1 { font-size: 30px; margin: 0 0 8px; }
.page-head.nested { margin: 28px 0 8px; }
.page-head.nested h2 { font-size: 20px; margin: 0 0 6px; font-family: var(--font-display); }
.sub { color: var(--text-secondary); margin: 0; line-height: 1.7; }
.status { margin: 12px 0 16px; padding: 10px 14px; border-radius: 10px; background: #fff7ed; color: #9a3412; font-size: 14px; }
.status.ok { background: #ecfdf5; color: #047857; }
.card-block {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow);
}
.card-block h2 { font-size: 16px; margin: 0 0 14px; }
.plan-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.plan {
  text-align: left;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  font: inherit;
}
.plan strong { display: block; font-size: 15px; }
.plan em { display: block; font-style: normal; color: var(--brand); font-size: 13px; margin: 4px 0; }
.plan span { display: block; font-size: 12px; color: var(--text-secondary); }
.plan.active { border-color: var(--brand); background: var(--brand-soft); }
.danger-zone { border-color: #fecaca; }
.legal-links { margin: 16px 0 0; font-size: 13px; color: var(--text-secondary); }
.card-block h2 { font-size: 16px; margin: 0 0 14px; }
.presets { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px; }
.preset {
  text-align: left;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  font: inherit;
}
.preset strong { display: block; font-size: 14px; }
.preset span { display: block; font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.preset.active { border-color: var(--brand); background: var(--brand-soft); }
.field { display: block; margin-bottom: 14px; }
.field span { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.field input, .field select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font: inherit;
}
.field small { display: block; margin-top: 6px; color: var(--text-secondary); font-size: 12px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.msg { font-size: 14px; margin: 0 0 12px; color: var(--success); }
.msg.err { color: var(--danger); }
</style>
