/** 浏览器语音通道：只负责听/说，不负责判分。 */

export function speak(text) {
  const payload = String(text || '').replace(/<[^>]+>/g, '').trim()
  if (!payload || typeof window === 'undefined' || !window.speechSynthesis) {
    return false
  }
  window.speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(payload.slice(0, 800))
  u.lang = 'zh-CN'
  u.rate = 1
  window.speechSynthesis.speak(u)
  return true
}

export function stopSpeak() {
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    window.speechSynthesis.cancel()
  }
}

export function canListen() {
  return typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition)
}

export function listenOnce() {
  return new Promise((resolve, reject) => {
    const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Ctor) {
      reject(new Error('当前浏览器不支持口答，请改用 Chrome / Edge，或直接打字。'))
      return
    }
    const rec = new Ctor()
    rec.lang = 'zh-CN'
    rec.interimResults = false
    rec.maxAlternatives = 1
    rec.onresult = (e) => {
      const text = e.results?.[0]?.[0]?.transcript || ''
      resolve(text)
    }
    rec.onerror = (e) => {
      reject(new Error(e.error === 'not-allowed' ? '请允许麦克风权限' : '没听清，请再试或改打字'))
    }
    rec.onend = () => {}
    rec.start()
  })
}
