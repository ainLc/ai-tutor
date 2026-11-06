import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import AppShell from './components/AppShell.vue'
import Home from './views/Home.vue'
import Learn from './views/Learn.vue'
import Login from './views/Login.vue'
import Dashboard from './views/Dashboard.vue'
import Review from './views/Review.vue'
import Settings from './views/Settings.vue'
import Defense from './views/Defense.vue'
import Certificate from './views/Certificate.vue'
import Legal from './views/Legal.vue'
import { getToken } from './api'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/legal/:doc', component: Legal },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', component: Home },
        { path: 'learn/:courseId', component: Learn },
        { path: 'defense/:courseId', component: Defense },
        { path: 'certificate/:defenseId', component: Certificate },
        { path: 'review', component: Review },
        { path: 'dashboard', component: Dashboard },
        { path: 'settings', component: Settings },
      ],
    },
  ],
})

// 路由守卫：未登录跳转到登录页
router.beforeEach((to) => {
  if (to.path.startsWith('/legal')) return true
  if (to.path !== '/login' && !getToken()) {
    return '/login'
  }
})

createApp(App).use(createPinia()).use(router).mount('#app')

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
