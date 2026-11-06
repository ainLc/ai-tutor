// API 封装（对应后端 /api）

const BASE = '/api'

export function getToken() {
  return localStorage.getItem('ai-tutor-token') || ''
}
export function setToken(t) {
  localStorage.setItem('ai-tutor-token', t)
}
export function clearToken() {
  localStorage.removeItem('ai-tutor-token')
}

function authHeaders(extra = {}) {
  const headers = { ...extra }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
}

async function request(path, options = {}) {
  const headers = authHeaders(options.headers || {})
  const res = await fetch(BASE + path, { ...options, headers })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      msg = data.detail || msg
    } catch (e) { /* ignore */ }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  if (res.status === 204) return null
  const text = await res.text()
  if (!text) return null
  return JSON.parse(text)
}

async function* readSse(res) {
  if (!res.ok || !res.body) {
    throw new Error(`流式请求失败 (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const evt of events) {
      const line = evt.trim()
      if (!line.startsWith('data:')) continue
      try {
        yield JSON.parse(line.slice(5).trim())
      } catch (e) { /* 忽略半截 JSON */ }
    }
  }
}

export const api = {
  register: (username, password, nickname) =>
    request('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, nickname }),
    }),
  login: (username, password) =>
    request('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  me: () => request('/auth/me'),
  deleteAccount: (confirm) =>
    request('/auth/me', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm }),
    }),
  getBilling: () => request('/billing/me'),
  switchPlan: (plan) =>
    request('/billing/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan }),
    }),
  circuitOverride: () =>
    request('/home/circuit-override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ acknowledge: true }),
    }),
  getLlmSettings: () => request('/settings/llm'),
  saveLlmSettings: (payload) =>
    request('/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  resetLlmSettings: () => request('/settings/llm', { method: 'DELETE' }),
  testLlmSettings: () => request('/settings/llm/test', { method: 'POST' }),

  dashboard: () => request('/dashboard'),
  today: () => request('/home/today'),
  reviewStats: () => request('/review/stats'),
  reviewToday: () => request('/review/today'),

  listCourses: () => request('/courses'),
  getCourse: (id) => request(`/courses/${id}`),
  deleteCourse: (id) => request(`/courses/${id}`, { method: 'DELETE' }),
  getLesson: (id) => request(`/lessons/${id}`),

  uploadCourse: async (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/courses/upload', { method: 'POST', body: form })
  },

  answerLesson: (lessonId, answer) =>
    request(`/lessons/${lessonId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lesson_id: lessonId, answer }),
    }),

  retestLesson: (lessonId) =>
    request(`/lessons/${lessonId}/retest`, { method: 'POST' }),

  listCards: (lessonId) => request(`/lessons/${lessonId}/cards`),
  createCards: (lessonId) => request(`/lessons/${lessonId}/cards`, { method: 'POST' }),
  deleteCard: (cardId) => request(`/cards/${cardId}`, { method: 'DELETE' }),
  reviewCard: (cardId, rating) =>
    request(`/cards/${cardId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    }),

  updateCourseSettings: (courseId, payload) =>
    request(`/courses/${courseId}/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  getChapterQuiz: (chapterId) => request(`/chapters/${chapterId}/quiz`),
  createChapterQuiz: (chapterId) =>
    request(`/chapters/${chapterId}/quiz`, { method: 'POST' }),
  answerChapterQuiz: (chapterId, index, answer) =>
    request(`/chapters/${chapterId}/quiz/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index, answer }),
    }),

  reportLesson: (lessonId, note = '') =>
    request(`/lessons/${lessonId}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'not_in_source', note }),
    }),
  pretestLesson: (lessonId) => request(`/lessons/${lessonId}/pretest`, { method: 'POST' }),
  pretestAnswer: (lessonId, answer) =>
    request(`/lessons/${lessonId}/pretest/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    }),

  shareCourse: (courseId) => request(`/share/${courseId}`, { method: 'POST' }),
  importShare: (token) =>
    request('/share/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }),

  getDefense: (courseId) => request(`/courses/${courseId}/defense`),
  startDefense: (courseId) => request(`/courses/${courseId}/defense`, { method: 'POST' }),
  answerDefense: (defenseId, index, answer) =>
    request(`/defense/${defenseId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index, answer }),
    }),
  getCertificate: (defenseId) => request(`/defense/${defenseId}/certificate`),

  async *streamLesson(lessonId) {
    const res = await fetch(`${BASE}/lessons/${lessonId}/stream`, { headers: authHeaders() })
    yield* readSse(res)
  },

  async *streamReteach(lessonId, answer, gap) {
    const res = await fetch(`${BASE}/lessons/${lessonId}/reteach/stream`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ answer, gap }),
    })
    yield* readSse(res)
  },
}
