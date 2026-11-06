<template>
  <div class="login-page">
    <div class="login-layout">
      <section class="manifesto">
        <div class="brand">
          <span class="logo-mark"></span>
          <span class="logo-text">AI 私教</span>
        </div>
        <h1 class="display">合上你的资料，两周后还要能讲</h1>
        <p>讲课已经商品化。这里卖的是：对着你这份资料过关，14 日还能提取，并且有一份刷不出来的证明。</p>
        <ul>
          <li>没有「已完成」，只有已理解 / 尚未记住 / 已记住</li>
          <li>今日到期超过 40 张，新课默认锁定</li>
          <li>合上书答辩通过后，出具一页掌握凭证</li>
        </ul>
        <div class="mini card">
          <DualProgress :understood="7" :total="9" :settled="3" :cards="12" label="已学过，尚未记住" />
        </div>
      </section>

      <div class="login-card">
        <h2>{{ isLogin ? '欢迎回来' : '创建账号' }}</h2>
        <p class="sub">{{ isLogin ? '先清该记的，再学新的。' : '上传将用于过关的那份资料。体验档 1 门课。' }}</p>

        <form @submit.prevent="submit">
          <div class="field">
            <label>用户名</label>
            <input v-model="username" type="text" placeholder="请输入用户名" required />
          </div>
          <div class="field" v-if="!isLogin">
            <label>昵称</label>
            <input v-model="nickname" type="text" placeholder="给自己起个昵称（可选）" />
          </div>
          <div class="field">
            <label>密码</label>
            <input v-model="password" type="password" placeholder="请输入密码（至少 6 位）" required />
          </div>

          <p v-if="error" class="error">{{ error }}</p>

          <button class="btn btn-submit" type="submit" :disabled="loading">
            {{ loading ? '请稍候…' : (isLogin ? '登录' : '注册并开始') }}
          </button>
        </form>

        <p class="switch">
          {{ isLogin ? '还没有账号？' : '已有账号？' }}
          <a @click="toggle">{{ isLogin ? '去注册' : '去登录' }}</a>
        </p>
        <p class="legal">
          <router-link to="/legal/privacy">隐私政策</router-link>
          ·
          <router-link to="/legal/terms">使用条款</router-link>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setToken } from '../api'
import DualProgress from '../components/DualProgress.vue'

const router = useRouter()
const isLogin = ref(true)
const username = ref('')
const nickname = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

function toggle() {
  isLogin.value = !isLogin.value
  error.value = ''
}

async function submit() {
  loading.value = true
  error.value = ''
  try {
    let res
    if (isLogin.value) {
      res = await api.login(username.value, password.value)
    } else {
      res = await api.register(username.value, password.value, nickname.value)
    }
    setToken(res.token)
    localStorage.setItem('ai-tutor-user', JSON.stringify({ username: res.username, nickname: res.nickname }))
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
}
.login-layout {
  width: min(980px, 100%);
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 28px;
  align-items: stretch;
}
.manifesto { padding: 12px 8px; }
.brand { display: flex; align-items: center; gap: 8px; margin-bottom: 28px; }
.logo-text { font-size: 20px; font-weight: 700; }
.manifesto h1 { font-size: 40px; line-height: 1.2; margin: 0 0 16px; }
.manifesto p { color: var(--text-secondary); margin: 0 0 16px; font-size: 16px; }
.manifesto ul { margin: 0 0 24px; padding-left: 18px; color: var(--text); }
.mini { max-width: 360px; }
.login-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 36px 32px;
  box-shadow: var(--shadow-lg);
}
.login-card h2 { font-size: 24px; margin: 0 0 6px; font-family: var(--font-display); }
.sub { color: var(--text-secondary); margin: 0 0 24px; font-size: 14px; }
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.field input {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 15px;
  background: #fff;
}
.field input:focus { outline: none; border-color: var(--brand); box-shadow: 0 0 0 3px rgba(79,70,229,0.12); }
.error { color: var(--danger); font-size: 13px; margin: 0 0 12px; }
.btn-submit { width: 100%; padding: 13px; font-size: 16px; }
.switch { text-align: center; margin-top: 18px; font-size: 14px; color: var(--text-secondary); }
.switch a { cursor: pointer; font-weight: 600; }
.legal { text-align: center; margin-top: 10px; font-size: 12px; color: var(--text-secondary); }
@media (max-width: 840px) {
  .login-layout { grid-template-columns: 1fr; }
  .manifesto h1 { font-size: 28px; }
}
</style>
