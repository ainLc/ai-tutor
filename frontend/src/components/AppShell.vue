<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="container topbar-inner">
        <div class="logo" role="button" @click="$router.push('/')">
          <span class="logo-mark"></span>
          <span class="logo-text">AI 私教</span>
          <span class="logo-sub desktop-only">合上资料仍会</span>
        </div>

        <nav class="desk-nav desktop-only">
          <router-link to="/" class="nav-link" :class="{ active: isToday }">今日</router-link>
          <router-link to="/review" class="nav-link" :class="{ active: $route.path === '/review' }">
            记忆练习
            <span v-if="dueCount" class="nav-badge">{{ dueCount }}</span>
          </router-link>
          <router-link to="/dashboard" class="nav-link" :class="{ active: $route.path === '/dashboard' }">掌握</router-link>
          <router-link to="/settings" class="nav-link" :class="{ active: $route.path === '/settings' }">设置</router-link>
        </nav>

        <div class="topbar-actions desktop-only">
          <button class="btn btn-ghost" @click="showImport = true">导入分享</button>
          <button class="btn" @click="showUpload = true">上传资料</button>
          <div class="user-chip">
            <span class="user-avatar">{{ userInitial }}</span>
            <span class="user-name">{{ user?.nickname || user?.username }}</span>
            <button class="logout" @click="logout">退出</button>
          </div>
        </div>

        <button class="mobile-avatar mobile-only" @click="showMenu = !showMenu">{{ userInitial }}</button>
      </div>
    </header>

    <div v-if="showMenu" class="mobile-menu" @click.self="showMenu = false">
      <div class="menu-item" @click="$router.push('/settings'); showMenu = false">设置</div>
      <div class="menu-item" @click="showImport = true; showMenu = false">导入分享</div>
      <div class="menu-item" @click="showUpload = true; showMenu = false">上传资料</div>
      <div class="menu-item" @click="logout">退出登录</div>
    </div>

    <div class="shell-body">
      <router-view />
    </div>

    <nav class="bottom-nav mobile-only">
      <div class="bn-item" :class="{ active: isToday }" @click="$router.push('/')">
        <span class="bn-dot"></span><span>今日</span>
      </div>
      <div class="bn-item" :class="{ active: $route.path === '/review' }" @click="$router.push('/review')">
        <span class="bn-dot"></span><span>复习{{ dueCount ? ` ${dueCount}` : '' }}</span>
      </div>
      <div class="bn-item" :class="{ active: $route.path === '/dashboard' }" @click="$router.push('/dashboard')">
        <span class="bn-dot"></span><span>掌握</span>
      </div>
      <div class="bn-item" @click="showUpload = true">
        <span class="bn-dot upload"></span><span>上传</span>
      </div>
    </nav>

    <div v-if="showUpload" class="modal-mask" @click.self="closeUpload">
      <div class="modal">
        <div class="modal-head">
          <h2>上传将用于过关的那份资料</h2>
          <button class="modal-close" @click="closeUpload">关闭</button>
        </div>
        <div class="dropzone" @click="pick" @dragover.prevent @drop.prevent="onDrop">
          <p v-if="!file" class="drop-text">点击选择，或把文件拖到这里<br /><span class="hint">支持 md / txt / zip / 文本 PDF。拆完你会看到章节树和「不懂不能过」。</span></p>
          <p v-else class="drop-text" style="font-weight:600">{{ file.name }}</p>
          <input ref="fileInput" type="file" accept=".md,.txt,.zip,.markdown,.pdf" style="display:none" @change="onSelect" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="closeUpload">取消</button>
          <button class="btn" @click="upload" :disabled="!file || uploading">{{ uploading ? 'AI 拆课中…' : '开始拆课' }}</button>
        </div>
        <p v-if="uploading" class="hint" style="margin:12px 0 0">资料稍长或扫描件自动识别时大约 1–3 分钟，请不要关闭窗口。</p>
        <p v-if="error" class="upload-error">{{ error }}</p>
      </div>
    </div>

    <div v-if="showImport" class="modal-mask" @click.self="showImport = false">
      <div class="modal">
        <div class="modal-head">
          <h2>导入分享的课程</h2>
          <button class="modal-close" @click="showImport = false">关闭</button>
        </div>
        <p class="import-hint">输入分享码，记忆进度从零开始，互不污染。</p>
        <input v-model="importToken" class="import-input" placeholder="请输入分享码" />
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showImport = false">取消</button>
          <button class="btn" @click="doImport" :disabled="!importToken.trim() || importing">{{ importing ? '导入中…' : '导入' }}</button>
        </div>
        <p v-if="importMsg" class="upload-error">{{ importMsg }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, clearToken } from '../api'

const route = useRoute()
const router = useRouter()
const user = ref(null)
const dueCount = ref(0)
const showMenu = ref(false)
const showUpload = ref(false)
const showImport = ref(false)
const file = ref(null)
const fileInput = ref(null)
const uploading = ref(false)
const error = ref('')
const importToken = ref('')
const importing = ref(false)
const importMsg = ref('')

const userInitial = computed(() => (user.value?.nickname || user.value?.username || '我').charAt(0))
const isToday = computed(() => route.path === '/')

provide('openUpload', () => { showUpload.value = true })
provide('refreshDue', loadDue)

onMounted(() => {
  const u = localStorage.getItem('ai-tutor-user')
  if (u) { try { user.value = JSON.parse(u) } catch (e) { /* ignore */ } }
  loadDue()
})

async function loadDue() {
  try {
    const today = await api.today()
    dueCount.value = today.due_count || 0
  } catch (e) { /* ignore */ }
}

function pick() { fileInput.value.click() }
function onSelect(e) { file.value = e.target.files[0] || null }
function onDrop(e) { file.value = e.dataTransfer.files[0] || null }
function closeUpload() { showUpload.value = false; file.value = null; error.value = '' }

async function upload() {
  if (!file.value) return
  uploading.value = true
  error.value = ''
  try {
    const course = await api.uploadCourse(file.value)
    closeUpload()
    router.push(`/learn/${course.id}`)
  } catch (e) { error.value = e.message } finally { uploading.value = false }
}

async function doImport() {
  importing.value = true
  importMsg.value = ''
  try {
    await api.importShare(importToken.value.trim())
    showImport.value = false
    importToken.value = ''
    router.push('/')
    window.location.reload()
  } catch (e) { importMsg.value = e.message } finally { importing.value = false }
}

function logout() {
  clearToken()
  localStorage.removeItem('ai-tutor-user')
  showMenu.value = false
  router.push('/login')
}
</script>

<style scoped>
.app-shell { min-height: 100vh; }
.shell-body { padding-bottom: 72px; }
.desk-nav { display: flex; align-items: center; gap: 4px; }
.nav-link {
  position: relative;
  padding: 8px 12px;
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
}
.nav-link:hover { background: #f1f5f9; color: var(--text); text-decoration: none; }
.nav-link.active { color: var(--brand); background: #eef2ff; }
.nav-badge {
  display: inline-block;
  margin-left: 4px;
  min-width: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--brand);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}
.mobile-avatar {
  width: 36px; height: 36px; border: none; border-radius: 50%;
  background: var(--brand); color: #fff; font-weight: 700; cursor: pointer;
}
@media (min-width: 769px) {
  .shell-body { padding-bottom: 0; }
  .bottom-nav { display: none; }
}
</style>
